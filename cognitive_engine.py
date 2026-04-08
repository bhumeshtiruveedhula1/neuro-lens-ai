from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import fmean, pstdev
from typing import Deque, Dict, List, Optional, Sequence

from calibration import summarize_plain_state
from ml.inference import FEATURE_COLUMNS, explain_prediction, predict_scores
from schema import (
    ExplanationItem,
    LiveState,
    MinuteTelemetryPayload,
    NotificationMessage,
    OnboardingProfile,
    StateLabel,
    ThresholdProfile,
    TodaySummary,
)

WINDOW_MINUTES = 5
ROLLING_ACTIVE_WINDOWS = 120

COMMUNICATION_KEYWORDS = ("slack", "teams", "gmail", "outlook", "discord", "mail", "meet", "zoom")
ENTERTAINMENT_KEYWORDS = ("youtube", "netflix", "spotify", "primevideo", "hotstar", "reels", "tiktok", "shorts")


def _safe_std(values: Sequence[float]) -> float:
    return pstdev(values) if len(values) >= 2 else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _encode_cycle(value: float, period: float) -> tuple[float, float]:
    angle = 2 * math.pi * (value / period)
    return math.sin(angle), math.cos(angle)


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _pooled_mean_std(windows: Sequence[MinuteTelemetryPayload], mean_key: str, std_key: str, count_key: str) -> tuple[float, float]:
    total_n = 0
    total_sum = 0.0
    total_sumsq = 0.0
    for window in windows:
        count = getattr(window, count_key)
        if count <= 0:
            continue
        mean = getattr(window, mean_key)
        std = getattr(window, std_key)
        total_n += count
        total_sum += mean * count
        total_sumsq += (std ** 2 + mean ** 2) * count

    if total_n <= 0:
        return 0.0, 0.0
    pooled_mean = total_sum / total_n
    pooled_variance = max(0.0, total_sumsq / total_n - pooled_mean ** 2)
    return round(pooled_mean, 4), round(math.sqrt(pooled_variance), 4)


def _domain_bucket(domain: Optional[str], profile: OnboardingProfile) -> str:
    domain = (domain or "").lower()
    if not domain:
        return "other"
    if any(token in domain for token in profile.focus_apps):
        return "focus"
    if any(token in domain for token in profile.communication_apps):
        return "communication"
    if any(token in domain for token in profile.entertainment_apps):
        return "entertainment"
    if any(token in domain for token in profile.distraction_apps):
        return "entertainment"
    if any(token in domain for token in COMMUNICATION_KEYWORDS):
        return "communication"
    if any(token in domain for token in ENTERTAINMENT_KEYWORDS):
        return "entertainment"
    return "other"


def _is_break_window(window: MinuteTelemetryPayload) -> bool:
    return window.idle_seconds >= 180 or (window.active_seconds <= 10 and window.idle_seconds >= 45)


@dataclass
class UserRuntimeState:
    windows: Deque[MinuteTelemetryPayload] = field(default_factory=lambda: deque(maxlen=180))
    recent_scores: Deque[dict] = field(default_factory=lambda: deque(maxlen=180))
    last_break_time: Optional[datetime] = None
    high_load_since: Optional[datetime] = None
    last_notification_time: Optional[datetime] = None


class CognitiveEngine:
    def __init__(self):
        self._state: Dict[str, UserRuntimeState] = defaultdict(UserRuntimeState)

    def append_window(self, user_id: str, window: MinuteTelemetryPayload) -> None:
        runtime = self._state[user_id]
        runtime.windows.append(window)
        if _is_break_window(window):
            runtime.last_break_time = window.timestamp

    def get_recent_windows(self, user_id: str, limit: int = WINDOW_MINUTES) -> List[MinuteTelemetryPayload]:
        runtime = self._state[user_id]
        return list(runtime.windows)[-limit:]

    def build_feature_vector(
        self,
        user_id: str,
        profile: OnboardingProfile,
        recent_windows: Sequence[MinuteTelemetryPayload],
        rolling_reference: Sequence[Dict[str, float]],
    ) -> Dict[str, float]:
        runtime = self._state[user_id]
        if not recent_windows:
            return {}

        now = recent_windows[-1].timestamp
        window_seconds = max(300.0, float(sum(window.window_duration_s for window in recent_windows)))
        total_keystrokes = sum(window.key_count for window in recent_windows)
        total_chars = sum(window.character_count or max(0, window.key_count - window.backspace_count) for window in recent_windows)
        total_backspaces = sum(window.backspace_count for window in recent_windows)

        mean_key_hold, std_key_hold = _pooled_mean_std(recent_windows, "mean_key_hold", "std_key_hold", "key_hold_samples")
        mean_interkey, std_interkey = _pooled_mean_std(recent_windows, "mean_interkey_latency", "std_interkey_latency", "interkey_samples")

        idle_seconds = sum(window.idle_seconds for window in recent_windows)
        typing_active_seconds = sum(window.typing_active_seconds for window in recent_windows)
        total_active_seconds = sum(window.active_seconds for window in recent_windows)
        total_tab_switches = sum(window.tab_switches for window in recent_windows)
        total_window_switches = sum(window.window_switches for window in recent_windows)
        idle_bursts = sum(window.idle_bursts for window in recent_windows)
        unique_domains = {window.active_domain for window in recent_windows if window.active_domain}
        backspace_series = [window.backspace_count for window in recent_windows]

        runtime_windows = list(runtime.windows)
        breaks_last_hour = sum(1 for window in runtime_windows[-60:] if _is_break_window(window))
        last_break_time = runtime.last_break_time or recent_windows[0].timestamp
        time_since_last_break = max(0.0, (now - last_break_time).total_seconds() / 60.0)

        session_length_minutes = 0.0
        for window in reversed(runtime_windows):
            session_length_minutes += window.window_duration_s / 60.0
            if _is_break_window(window):
                break

        bucket_seconds = {"focus": 0.0, "communication": 0.0, "entertainment": 0.0}
        short_video_seconds = 0.0
        short_video_sessions = 0
        for window in recent_windows:
            bucket = _domain_bucket(window.active_domain, profile)
            if bucket in bucket_seconds:
                bucket_seconds[bucket] += window.active_seconds
            short_video_seconds += window.short_video_seconds
            short_video_sessions += window.short_video_sessions

        typing_speed_cpm = (total_chars / max(window_seconds, 1.0)) * 60.0
        error_rate = total_backspaces / max(total_keystrokes, 1)
        activity_ratio = typing_active_seconds / max(window_seconds, 1.0)
        switches_per_min = total_tab_switches / max(window_seconds / 60.0, 1.0)
        fragmentation_index = switches_per_min / max(activity_ratio, 0.05)
        avg_focus_duration_on_app = total_active_seconds / max(len(unique_domains) + total_tab_switches, 1)

        weekday = recent_windows[-1].timestamp.weekday()
        work_start_minutes = profile.workday_start_hour * 60.0
        current_minutes = recent_windows[-1].timestamp.hour * 60.0 + recent_windows[-1].timestamp.minute
        hours_since_work_start = max(0.0, (current_minutes - work_start_minutes) / 60.0)
        tod_sin, tod_cos = _encode_cycle(current_minutes, 24 * 60)
        dow_sin, dow_cos = _encode_cycle(weekday, 7)

        break_style_map = {
            "short_sprints": 0.0,
            "balanced": 0.5,
            "long_focus": 1.0,
        }

        features = {
            "mean_key_hold": mean_key_hold,
            "std_key_hold": std_key_hold,
            "mean_interkey_latency": mean_interkey,
            "std_interkey_latency": std_interkey,
            "typing_speed_cpm": round(typing_speed_cpm, 4),
            "error_rate": round(error_rate, 6),
            "error_burstiness": round(_variance(backspace_series), 6),
            "keystroke_activity_ratio": round(activity_ratio, 6),
            "tab_switches_per_min": round(switches_per_min, 6),
            "window_switches_per_min": round(total_window_switches / max(window_seconds / 60.0, 1.0), 6),
            "unique_domains": float(len(unique_domains)),
            "avg_focus_duration_on_app": round(avg_focus_duration_on_app, 6),
            "fragmentation_index": round(fragmentation_index, 6),
            "idle_seconds": round(idle_seconds, 4),
            "idle_ratio": round(idle_seconds / max(window_seconds, 1.0), 6),
            "num_idle_bursts": float(idle_bursts),
            "current_session_length_min": round(session_length_minutes, 4),
            "num_breaks_last_hour": float(breaks_last_hour),
            "time_since_last_break_min": round(time_since_last_break, 4),
            "seconds_in_focus_apps": round(bucket_seconds["focus"], 4),
            "seconds_in_communication_apps": round(bucket_seconds["communication"], 4),
            "seconds_in_entertainment_apps": round(bucket_seconds["entertainment"], 4),
            "entertainment_ratio": round(bucket_seconds["entertainment"] / max(window_seconds, 1.0), 6),
            "comms_ratio": round(bucket_seconds["communication"] / max(window_seconds, 1.0), 6),
            "short_video_seconds": round(short_video_seconds, 4),
            "short_video_sessions": float(short_video_sessions),
            "time_of_day_sin": round(tod_sin, 6),
            "time_of_day_cos": round(tod_cos, 6),
            "day_of_week_sin": round(dow_sin, 6),
            "day_of_week_cos": round(dow_cos, 6),
            "hours_since_work_start": round(hours_since_work_start, 6),
            "baseline_fatigue_week": profile.baseline_fatigue_week,
            "baseline_stress_week": profile.baseline_stress_week,
            "deep_focus_capacity_min": float(profile.deep_focus_capacity_min),
            "preferred_work_cycle_min": float(profile.preferred_work_cycle_min),
            "focus_capacity_minutes": float(profile.focus_capacity_minutes),
            "break_style_score": break_style_map.get(profile.break_style.value, 0.5),
            "user_target_hours": float(profile.user_target_hours),
            "context_switch_sensitivity": profile.context_switch_sensitivity,
            "avg_sleep_hours": profile.avg_sleep_hours,
            "last_night_sleep_hours": profile.last_night_sleep_hours,
            "focus_app_flag": 1.0 if bucket_seconds["focus"] > 0 else 0.0,
            "distraction_app_flag": 1.0 if bucket_seconds["entertainment"] > 0 else 0.0,
        }

        for feature_name in FEATURE_COLUMNS:
            if feature_name not in features and not feature_name.startswith(("z_", "rolling_mean_", "rolling_std_")):
                features[feature_name] = 0.0

        reference_map = {name: [] for name in features.keys() if not name.startswith(("z_", "rolling_mean_", "rolling_std_"))}
        for row in rolling_reference:
            for key in reference_map:
                if key in row:
                    reference_map[key].append(row[key])

        for key, current in list(features.items()):
            if key not in reference_map:
                continue
            values = reference_map[key][-ROLLING_ACTIVE_WINDOWS:]
            rolling_mean = fmean(values) if values else current
            rolling_std = _safe_std(values)
            features[f"rolling_mean_{key}"] = round(rolling_mean, 6)
            features[f"rolling_std_{key}"] = round(rolling_std, 6)
            features[f"z_{key}"] = round((current - rolling_mean) / rolling_std, 6) if rolling_std > 1e-6 else 0.0

        return features

    def model_maturity(self, profile: OnboardingProfile, total_predictions: int, distinct_days: int) -> float:
        target_windows = max(1, profile.learning_period_days * 8 * 60)
        maturity_by_windows = total_predictions / target_windows
        maturity_by_days = distinct_days / max(profile.learning_period_days, 1)
        return round(_clamp(0.65 * maturity_by_windows + 0.35 * maturity_by_days, 0.0, 1.0), 4)

    def derive_state(
        self,
        user_id: str,
        timestamp: datetime,
        profile: OnboardingProfile,
        features: Dict[str, float],
        maturity: float,
        burnout_risk_index: float,
        thresholds: ThresholdProfile,
        today_summary: TodaySummary,
    ) -> tuple[LiveState, Optional[NotificationMessage], dict]:
        scores = predict_scores(features, maturity=maturity)
        fatigue_score = scores["fatigue_score"]
        load_score = scores["load_score"]
        severity = max(fatigue_score, load_score, burnout_risk_index)

        if severity > thresholds.fatigued_max:
            state_label = StateLabel.BURNOUT_RISK
        elif severity > thresholds.high_load_max:
            state_label = StateLabel.FATIGUED
        elif severity > thresholds.normal_max:
            state_label = StateLabel.HIGH_LOAD
        else:
            state_label = StateLabel.NORMAL

        explanations = explain_prediction(features, scores, max_items=5)
        insight_strings = [item.reason for item in explanations[:3]]
        if maturity < 1.0:
            insight_strings.append("I’m still learning your rhythm, so I’ll keep the first-week nudges gentle.")

        notification = self._maybe_create_notification(
            user_id=user_id,
            timestamp=timestamp,
            profile=profile,
            state_label=state_label,
            confidence=scores["confidence"],
            maturity=maturity,
            explanations=explanations,
            burnout_risk_index=burnout_risk_index,
        )

        state = LiveState(
            user_id=user_id,
            timestamp=timestamp.isoformat(),
            state_label=state_label,
            fatigue_score=fatigue_score,
            load_score=load_score,
            confidence=scores["confidence"],
            model_maturity=maturity,
            burnout_risk_index=burnout_risk_index,
            p_fatigue=scores["p_fatigue"],
            p_high_load=scores["p_high_load"],
            explanation=explanations,
            insights=insight_strings,
            current_features={key: round(float(value), 6) for key, value in features.items() if not key.startswith("rolling_std_")},
            history_minutes=[],
            notification=notification,
            thresholds=thresholds,
            plain_summary=summarize_plain_state(severity, thresholds),
            today_summary=today_summary,
        )
        runtime = self._state[user_id]
        runtime.recent_scores.append(
            {
                "timestamp": timestamp,
                "state_label": state_label.value,
                "fatigue_score": fatigue_score,
                "load_score": load_score,
                "confidence": scores["confidence"],
            }
        )
        return state, notification, scores

    def _maybe_create_notification(
        self,
        user_id: str,
        timestamp: datetime,
        profile: OnboardingProfile,
        state_label: StateLabel,
        confidence: float,
        maturity: float,
        explanations: List[ExplanationItem],
        burnout_risk_index: float,
    ) -> Optional[NotificationMessage]:
        runtime = self._state[user_id]
        if not profile.alerts_enabled or confidence < 0.58:
            return None

        if state_label in {StateLabel.HIGH_LOAD, StateLabel.FATIGUED, StateLabel.BURNOUT_RISK}:
            runtime.high_load_since = runtime.high_load_since or timestamp
        else:
            runtime.high_load_since = None
            return None

        sustained_minutes = (timestamp - runtime.high_load_since).total_seconds() / 60.0 if runtime.high_load_since else 0.0
        cooldown_minutes = 30 if maturity < 1.0 else 50
        if runtime.last_notification_time and (timestamp - runtime.last_notification_time).total_seconds() / 60.0 < cooldown_minutes:
            return None

        threshold_minutes = 45 if state_label == StateLabel.HIGH_LOAD else 25
        if sustained_minutes < threshold_minutes:
            return None

        runtime.last_notification_time = timestamp
        top_reason = explanations[0].reason if explanations else "your pattern looks heavier than usual"
        if state_label == StateLabel.BURNOUT_RISK or burnout_risk_index >= 80:
            title = "Gentle reset idea"
            body = "You’ve been carrying a lot for a while. A longer break or an easier block could really help."
            severity = "critical"
            kind = "daily_burnout"
        elif state_label == StateLabel.FATIGUED:
            title = "Take a 3-minute pause"
            body = f"You’ve been pushing hard for a while. {top_reason.capitalize()}. Want a short reset?"
            severity = "high"
            kind = "break"
        else:
            title = "Maybe switch gears for a moment"
            body = f"You’ve been in a heavy zone for about {round(sustained_minutes)} minutes. {top_reason.capitalize()}."
            severity = "medium"
            kind = "task_switch"

        return NotificationMessage(
            title=title,
            body=body,
            severity=severity,
            kind=kind,
            created_at=timestamp.isoformat(),
        )

    def build_history_strip(self, user_id: str, limit: int = 18) -> List[Dict[str, float]]:
        runtime = self._state[user_id]
        history = list(runtime.recent_scores)[-limit:]
        return [
            {
                "timestamp": item["timestamp"].isoformat(),
                "fatigue_score": item["fatigue_score"],
                "load_score": item["load_score"],
                "confidence": item["confidence"],
            }
            for item in history
        ]


ENGINE = CognitiveEngine()
