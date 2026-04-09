from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from data.schema import EventType, RawEvent
from features.windowing import EventWindow

LONG_BREAK_IDLE_SECONDS = 180.0

FEATURE_KEYS_FOR_ZSCORE = [
    "typing_speed",
    "mean_hold_time",
    "mean_interkey_latency",
    "error_rate",
    "error_burstiness",
    "switches_per_minute",
    "unique_apps_count",
    "fragmentation_index",
    "idle_ratio",
    "session_duration",
    "time_since_last_break",
    "break_count",
    "hour_of_day",
    "day_of_week",
    "time_focus_category",
    "time_communication_category",
    "time_entertainment_category",
    "entertainment_ratio",
]

ROC_FEATURE_KEYS = [
    "typing_speed",
    "mean_interkey_latency",
    "error_rate",
    "switches_per_minute",
    "idle_ratio",
    "entertainment_ratio",
    "session_duration",
]

APP_CATEGORY_DEFAULT = "other"

APP_CATEGORY_COMMUNICATION_KEYWORDS = (
    "slack",
    "teams",
    "gmail",
    "outlook",
    "discord",
    "meet",
    "zoom",
)

APP_CATEGORY_ENTERTAINMENT_KEYWORDS = (
    "youtube",
    "netflix",
    "spotify",
    "primevideo",
    "hotstar",
    "tiktok",
    "reels",
    "shorts",
)


def _safe_mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def _safe_variance(values: Iterable[float]) -> float:
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return float(sum((value - mean) ** 2 for value in vals) / len(vals))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _cyclic_encode(value: float, period: float) -> Tuple[float, float]:
    angle = 2.0 * math.pi * (value / period)
    return math.sin(angle), math.cos(angle)


def _normalize_category(event: RawEvent) -> str:
    if event.app_category:
        category = event.app_category.lower()
        if category in {"focus", "communication", "entertainment", "other"}:
            return category
    app_name = (event.app_name or "").lower()
    if any(token in app_name for token in APP_CATEGORY_COMMUNICATION_KEYWORDS):
        return "communication"
    if any(token in app_name for token in APP_CATEGORY_ENTERTAINMENT_KEYWORDS):
        return "entertainment"
    return APP_CATEGORY_DEFAULT


def _is_break_event(event: RawEvent) -> bool:
    if event.session_break_flag > 0:
        return True
    if event.event_type == EventType.IDLE and event.idle_seconds >= LONG_BREAK_IDLE_SECONDS:
        return True
    return False


def _typing_activity_seconds(typing_events: List[RawEvent], window_seconds: float) -> float:
    if not typing_events:
        return 0.0
    estimated = 0.0
    for event in typing_events:
        latency_ms = event.inter_key_latency if event.inter_key_latency is not None else 180.0
        estimated += min(float(latency_ms), 2000.0) / 1000.0
    return _clamp(estimated, 0.0, window_seconds)


def _error_burstiness(typing_events: List[RawEvent], window_start: datetime, window_minutes: int) -> float:
    if not typing_events or window_minutes <= 0:
        return 0.0
    minute_buckets = [0 for _ in range(window_minutes)]
    for event in typing_events:
        if event.error_flag <= 0:
            continue
        minute_index = int((event.timestamp - window_start).total_seconds() // 60.0)
        minute_index = int(_clamp(float(minute_index), 0.0, float(window_minutes - 1)))
        minute_buckets[minute_index] += 1
    return _safe_variance(minute_buckets)


def _estimate_category_seconds(
    events: List[RawEvent],
    window_start: datetime,
    window_end: datetime,
    initial_category: str,
) -> Tuple[Dict[str, float], str]:
    totals = {
        "focus": 0.0,
        "communication": 0.0,
        "entertainment": 0.0,
        "other": 0.0,
    }

    if window_end <= window_start:
        return totals, initial_category

    ordered = sorted(events, key=lambda item: item.timestamp)
    active_category = initial_category if initial_category in totals else APP_CATEGORY_DEFAULT
    cursor = window_start

    for event in ordered:
        point = min(max(event.timestamp, window_start), window_end)
        if point > cursor:
            totals[active_category] += (point - cursor).total_seconds()
            cursor = point
        category = _normalize_category(event)
        if category in totals:
            active_category = category

    if window_end > cursor:
        totals[active_category] += (window_end - cursor).total_seconds()

    return totals, active_category


@dataclass
class FeatureRuntimeContext:
    previous_features: Dict[str, float] = field(default_factory=dict)
    session_start_at: Optional[datetime] = None
    last_break_at: Optional[datetime] = None
    last_active_category: str = APP_CATEGORY_DEFAULT


def compute_window_features(window: EventWindow, context: FeatureRuntimeContext) -> Dict[str, float]:
    """
    Build model-ready features from one 5-minute sliding window.

    Includes:
    - Core features required by locked design.
    - Rate-of-change features vs previous window.
    - Compatibility aliases used by existing realtime endpoints.
    """
    ordered = sorted(window.events, key=lambda item: item.timestamp)
    window_seconds = max((window.end - window.start).total_seconds(), 1.0)
    window_minutes = max(int(round(window_seconds / 60.0)), 1)

    typing_events = [event for event in ordered if event.event_type == EventType.KEYSTROKE]
    app_switch_events = [event for event in ordered if event.event_type == EventType.APP_SWITCH]
    idle_events = [event for event in ordered if event.event_type == EventType.IDLE]
    break_events = [event for event in ordered if _is_break_event(event)]

    total_keystrokes = len(typing_events)
    total_errors = sum(1 for event in typing_events if event.error_flag > 0)

    mean_hold_time = _safe_mean(
        event.key_hold_time for event in typing_events if event.key_hold_time is not None
    )
    mean_interkey_latency = _safe_mean(
        event.inter_key_latency for event in typing_events if event.inter_key_latency is not None
    )

    typing_speed = float(total_keystrokes) / (window_seconds / 60.0)
    typing_activity_seconds = _typing_activity_seconds(typing_events, window_seconds)
    typing_activity_ratio = typing_activity_seconds / window_seconds
    switches_per_minute = float(len(app_switch_events)) / (window_seconds / 60.0)

    unique_apps_count = float(len({event.app_name for event in ordered if event.app_name}))
    error_rate = float(total_errors) / max(total_keystrokes, 1)
    error_burstiness = _error_burstiness(typing_events, window.start, window_minutes)
    fragmentation_index = switches_per_minute / max(typing_activity_ratio, 0.01)

    idle_seconds = sum(float(event.idle_seconds) for event in idle_events)
    if not ordered:
        idle_seconds = window_seconds
    idle_ratio = _clamp(idle_seconds / window_seconds, 0.0, 1.0)

    if context.session_start_at is None:
        context.session_start_at = window.start
    if break_events:
        latest_break = max(event.timestamp for event in break_events)
        context.last_break_at = latest_break
        context.session_start_at = latest_break

    day_start = window.end.replace(hour=0, minute=0, second=0, microsecond=0)
    session_anchor = context.session_start_at or day_start
    session_duration = max(0.0, (window.end - max(session_anchor, day_start)).total_seconds() / 60.0)
    if context.last_break_at:
        time_since_last_break = max(0.0, (window.end - context.last_break_at).total_seconds() / 60.0)
    else:
        time_since_last_break = max(0.0, (window.end - max(day_start, session_anchor)).total_seconds() / 60.0)
    break_count = float(len(break_events))

    category_seconds, last_category = _estimate_category_seconds(
        ordered,
        window_start=window.start,
        window_end=window.end,
        initial_category=context.last_active_category,
    )
    context.last_active_category = last_category

    hour_of_day = float(window.end.hour) + float(window.end.minute) / 60.0
    tod_sin, tod_cos = _cyclic_encode(hour_of_day, 24.0)
    day_of_week = float(window.end.weekday())
    dow_sin, dow_cos = _cyclic_encode(day_of_week, 7.0)

    feature_vector = {
        "typing_speed": round(typing_speed, 6),
        "mean_hold_time": round(mean_hold_time, 6),
        "mean_interkey_latency": round(mean_interkey_latency, 6),
        "error_rate": round(error_rate, 6),
        "error_burstiness": round(error_burstiness, 6),
        "switches_per_minute": round(switches_per_minute, 6),
        "unique_apps_count": round(unique_apps_count, 6),
        "fragmentation_index": round(fragmentation_index, 6),
        "idle_ratio": round(idle_ratio, 6),
        "session_duration": round(session_duration, 6),
        "time_since_last_break": round(time_since_last_break, 6),
        "break_count": round(break_count, 6),
        "hour_of_day": round(hour_of_day, 6),
        "time_of_day_sin": round(tod_sin, 6),
        "time_of_day_cos": round(tod_cos, 6),
        "day_of_week": round(day_of_week, 6),
        "day_of_week_sin": round(dow_sin, 6),
        "day_of_week_cos": round(dow_cos, 6),
        "time_focus_category": round(category_seconds["focus"], 6),
        "time_communication_category": round(category_seconds["communication"], 6),
        "time_entertainment_category": round(category_seconds["entertainment"], 6),
        "time_other_category": round(category_seconds["other"], 6),
        "entertainment_ratio": round(category_seconds["entertainment"] / window_seconds, 6),
        "typing_activity_ratio": round(typing_activity_ratio, 6),
    }

    # Compatibility aliases for existing runtime scoring stack.
    feature_vector["typing_speed_cpm"] = feature_vector["typing_speed"]
    feature_vector["mean_key_hold"] = feature_vector["mean_hold_time"]
    feature_vector["tab_switches_per_min"] = feature_vector["switches_per_minute"]
    feature_vector["unique_domains"] = feature_vector["unique_apps_count"]
    feature_vector["keystroke_activity_ratio"] = feature_vector["typing_activity_ratio"]
    feature_vector["current_session_length_min"] = feature_vector["session_duration"]
    feature_vector["time_since_last_break_min"] = feature_vector["time_since_last_break"]
    feature_vector["num_breaks_last_hour"] = feature_vector["break_count"]
    feature_vector["seconds_in_focus_apps"] = feature_vector["time_focus_category"]
    feature_vector["seconds_in_communication_apps"] = feature_vector["time_communication_category"]
    feature_vector["seconds_in_entertainment_apps"] = feature_vector["time_entertainment_category"]

    for base_name in ROC_FEATURE_KEYS:
        current = feature_vector.get(base_name, 0.0)
        previous = context.previous_features.get(base_name)
        if previous is None:
            roc = 0.0
        elif abs(previous) < 1e-6:
            roc = current - previous
        else:
            roc = (current - previous) / abs(previous)
        feature_vector[f"roc_{base_name}"] = round(float(roc), 6)

    context.previous_features = {
        key: float(value) for key, value in feature_vector.items() if isinstance(value, (int, float))
    }
    return feature_vector
