from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from backend.core.schema import LiveState

CALIBRATION_POINT_THRESHOLD = 10
STALE_AFTER_MINUTES = 10
TREND_WINDOW = 12

BEHAVIOR_FEATURES = {
    "typing_speed",
    "inter_key_latency_mean",
    "inter_key_latency_std",
    "hold_time_mean",
    "error_rate",
    "error_burstiness",
    "switches_per_minute",
    "app_usage_per_minute",
    "z_typing_speed",
    "z_inter_key_latency_mean",
    "z_error_rate",
    "z_switches_per_minute",
}

SESSION_FEATURES = {
    "idle_ratio",
    "session_duration_min",
    "time_since_last_break",
    "cumulative_work_time",
    "z_idle_ratio",
    "z_session_duration_min",
}

FATIGUE_FEATURES = {
    "fatigue_accumulation_index",
    "typing_speed_trend",
    "error_rate_trend",
    "switching_trend",
    "z_fatigue_accumulation_index",
}

STATE_MAP = {
    "Normal": "normal",
    "High Load": "high_load",
    "Fatigued": "fatigue",
    "Burnout Risk": "risk",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _unique(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _feature_value(features: Dict[str, Any], names: Sequence[str], default: float = 0.0) -> float:
    for name in names:
        value = features.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return float(default)


def _history_mean(feature_windows: Sequence[Dict[str, Any]], names: Sequence[str], fallback: float) -> float:
    values: List[float] = []
    for row in feature_windows:
        for name in names:
            value = row.get(name)
            if value is None:
                continue
            try:
                values.append(float(value))
                break
            except Exception:
                continue
    if not values:
        return float(fallback)
    return sum(values) / len(values)


def build_baselines(
    current_features: Dict[str, Any],
    feature_windows: Sequence[Dict[str, Any]],
) -> Dict[str, float]:
    current_typing = _feature_value(current_features, ("typing_speed", "typing_speed_cpm"))
    current_error = _feature_value(current_features, ("error_rate",))
    current_switching = _feature_value(current_features, ("switches_per_minute", "tab_switches_per_min"))

    typing_baseline = current_features.get("rolling_mean_typing_speed")
    if typing_baseline is None:
        typing_baseline = current_features.get("rolling_mean_typing_speed_cpm")
    error_baseline = current_features.get("rolling_mean_error_rate")
    switching_baseline = current_features.get("rolling_mean_switches_per_minute")
    if switching_baseline is None:
        switching_baseline = current_features.get("rolling_mean_tab_switches_per_min")

    if typing_baseline is None:
        typing_baseline = _history_mean(feature_windows, ("typing_speed", "typing_speed_cpm"), current_typing)
    if error_baseline is None:
        error_baseline = _history_mean(feature_windows, ("error_rate",), current_error)
    if switching_baseline is None:
        switching_baseline = _history_mean(feature_windows, ("switches_per_minute", "tab_switches_per_min"), current_switching)

    return {
        "typing_speed": round(float(typing_baseline), 2),
        "error_rate": round(float(error_baseline), 4),
        "switching": round(float(switching_baseline), 3),
    }


def build_reason_groups(state: LiveState, current_features: Dict[str, Any]) -> Dict[str, List[str]]:
    behavior: List[str] = []
    session: List[str] = []
    fatigue: List[str] = []

    for item in state.explanation:
        reason = item.reason
        feature = item.feature
        if feature in SESSION_FEATURES:
            session.append(reason)
        elif feature in FATIGUE_FEATURES:
            fatigue.append(reason)
        elif feature in BEHAVIOR_FEATURES:
            behavior.append(reason)
        else:
            fatigue.append(reason)

    idle_ratio = _feature_value(current_features, ("idle_ratio",))
    session_minutes = _feature_value(current_features, ("session_duration_min", "current_session_length_min"))
    if idle_ratio >= 0.2:
        session.append("idle time is elevated")
    if session_minutes >= 90:
        session.append("the session has stretched beyond a healthy focus block")
    if state.burnout_risk_index >= 70:
        fatigue.append("burnout pressure is elevated")
    if state.drowsy_flag:
        fatigue.append("eye signals suggest drowsiness")
    if not behavior:
        behavior.append("behavioral signals are close to recent baseline")
    if not session:
        session.append("session pacing is within a normal range")
    if not fatigue:
        fatigue.append(state.plain_summary)

    return {
        "behavior": _unique(behavior)[:4],
        "session": _unique(session)[:4],
        "fatigue": _unique(fatigue)[:4],
    }


def build_trend(
    history: Sequence[Dict[str, Any]],
    current_score: float,
) -> Tuple[str, float]:
    if history:
        scores = [
            max(float(row.get("fatigue_score", 0.0)), float(row.get("load_score", 0.0)))
            for row in history[-TREND_WINDOW:]
        ]
    else:
        scores = []

    if not scores:
        return "stable", 0.0

    latest_score = scores[-1]
    if abs(latest_score - current_score) > 0.01:
        scores.append(float(current_score))

    if len(scores) < 2:
        return "stable", 0.0

    delta = float(scores[-1] - scores[0])
    if delta >= 4.0:
        direction = "up"
    elif delta <= -4.0:
        direction = "down"
    else:
        direction = "stable"
    return direction, round(delta, 2)


def build_distraction_level(current_features: Dict[str, Any], baselines: Dict[str, float]) -> float:
    switching = _feature_value(current_features, ("switches_per_minute", "tab_switches_per_min"))
    app_usage = _feature_value(current_features, ("app_usage_per_minute",))
    idle_ratio = _feature_value(current_features, ("idle_ratio",))

    baseline_switching = max(float(baselines.get("switching", 0.0)), 0.1)
    switch_ratio = switching / baseline_switching

    switch_score = _clamp((switch_ratio - 1.0) * 30.0 + (switching / 4.0) * 35.0, 0.0, 45.0)
    app_score = _clamp((app_usage / 15.0) * 25.0, 0.0, 25.0)
    idle_score = _clamp((idle_ratio / 0.35) * 30.0, 0.0, 30.0)
    return round(_clamp(switch_score + app_score + idle_score, 0.0, 100.0), 2)


def build_anomalies(current_features: Dict[str, Any], baselines: Dict[str, float]) -> List[str]:
    anomalies: List[str] = []

    typing_speed = _feature_value(current_features, ("typing_speed", "typing_speed_cpm"))
    error_rate = _feature_value(current_features, ("error_rate",))
    switching = _feature_value(current_features, ("switches_per_minute", "tab_switches_per_min"))
    idle_ratio = _feature_value(current_features, ("idle_ratio",))
    app_usage = _feature_value(current_features, ("app_usage_per_minute",))
    session_minutes = _feature_value(current_features, ("session_duration_min", "current_session_length_min"))

    z_typing = _feature_value(current_features, ("z_typing_speed",))
    z_error = _feature_value(current_features, ("z_error_rate",))
    z_switching = _feature_value(current_features, ("z_switches_per_minute",))
    z_idle = _feature_value(current_features, ("z_idle_ratio",))
    z_session = _feature_value(current_features, ("z_session_duration_min",))

    if z_typing <= -1.5 or typing_speed < max(float(baselines.get("typing_speed", 0.0)) * 0.75, 1.0):
        anomalies.append("typing speed dropped below baseline")
    if z_error >= 1.5 or error_rate > max(float(baselines.get("error_rate", 0.0)) * 1.8, 0.12):
        anomalies.append("error rate spiked above baseline")
    if z_switching >= 1.5 or switching > max(float(baselines.get("switching", 0.0)) * 1.6, 2.5):
        anomalies.append("context switching is unusually high")
    if z_idle >= 1.5 or idle_ratio >= 0.22:
        anomalies.append("idle time is higher than normal")
    if app_usage >= 14.0:
        anomalies.append("app activity density is unusually high")
    if z_session >= 1.5 or session_minutes >= 100.0:
        anomalies.append("session length is above your normal range")

    return _unique(anomalies)


def build_actions(
    state_key: str,
    trend: str,
    burnout_score: float,
    distraction_level: float,
    anomalies: Sequence[str],
) -> List[str]:
    actions: List[str] = []

    if state_key == "risk":
        actions.extend(
            [
                "Step away and reset",
                "Reduce workload for the next block",
            ]
        )
    elif state_key == "fatigue":
        actions.extend(
            [
                "Step away and reset",
                "Take a longer recovery break before deep work",
            ]
        )
    elif state_key == "high_load" and trend == "up":
        actions.append("Take a short break")
    elif state_key == "high_load":
        actions.append("Finish the current task before switching context")
    else:
        actions.append("Continue focus")

    if distraction_level >= 65:
        actions.append("Reduce tab and app switching for the next block")
    if burnout_score >= 70:
        actions.append("Protect recovery time and avoid another long session")
    if any("idle time" in item.lower() for item in anomalies):
        actions.append("Reset attention with hydration or a quick walk")

    return _unique(actions)[:4]


def build_status(last_updated: str, prediction_count: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if prediction_count < CALIBRATION_POINT_THRESHOLD:
        return "calibrating"
    age_minutes = max(0.0, (now - _parse_timestamp(last_updated)).total_seconds() / 60.0)
    if age_minutes > STALE_AFTER_MINUTES:
        return "stale"
    return "live"


def normalize_confidence(state: LiveState) -> str:
    level = str(state.confidence_level or "").lower()
    if level in {"low", "medium", "high"}:
        return level
    if state.confidence < 0.45:
        return "low"
    if state.confidence < 0.72:
        return "medium"
    return "high"


def map_live_state_to_ui(
    *,
    state: LiveState,
    current_features: Dict[str, Any],
    feature_windows: Sequence[Dict[str, Any]],
    history: Sequence[Dict[str, Any]],
    prediction_count: int,
    now: datetime | None = None,
) -> Dict[str, Any]:
    now = now or datetime.now(UTC)
    fatigue_score = _clamp(
        float(state.final_fatigue_score or max(state.fatigue_score, state.load_score)),
        0.0,
        100.0,
    )
    state_key = STATE_MAP.get(state.state_label.value, "normal")
    baselines = build_baselines(current_features, feature_windows)
    trend, trend_delta = build_trend(history, fatigue_score)
    burnout_score = round(_clamp(float(state.burnout_risk_index), 0.0, 100.0), 2)
    distraction_level = build_distraction_level(current_features, baselines)
    anomalies = build_anomalies(current_features, baselines)
    actions = build_actions(state_key, trend, burnout_score, distraction_level, anomalies)

    return {
        "fatigue_score": round(fatigue_score, 2),
        "state": state_key,
        "confidence": normalize_confidence(state),
        "reasons": build_reason_groups(state, current_features),
        "trend": trend,
        "trendDelta": trend_delta,
        "burnoutScore": burnout_score,
        "distractionLevel": distraction_level,
        "baselines": baselines,
        "anomalies": anomalies,
        "actions": actions,
        "last_updated": state.timestamp,
        "status": build_status(state.timestamp, prediction_count, now=now),
    }


def build_demo_ui_payload(now: datetime | None = None) -> Dict[str, Any]:
    now = now or datetime.now(UTC)
    timestamp = now.isoformat()
    return {
        "fatigue_score": 34.0,
        "state": "normal",
        "confidence": "medium",
        "reasons": {
            "behavior": ["demo mode is using synthetic behavioral signals"],
            "session": ["no live telemetry is available yet"],
            "fatigue": ["baseline fatigue pressure is currently light"],
        },
        "trend": "stable",
        "trendDelta": 0.0,
        "burnoutScore": 18.0,
        "distractionLevel": 22.0,
        "baselines": {
            "typing_speed": 220.0,
            "error_rate": 0.03,
            "switching": 0.8,
        },
        "anomalies": ["running in demo mode without real telemetry"],
        "actions": ["Continue focus"],
        "last_updated": timestamp,
        "status": "calibrating",
    }
