from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Sequence

from backend.core.fusion import FusionResult, build_realtime_alerts, fuse_scores
from backend.core.model_c_eye import EyeFatigueResult, ModelCEyeFatigue
from backend.core.schema import MinuteTelemetryPayload, OnboardingProfile

logger = logging.getLogger(__name__)


TRACKING_REQUIREMENTS: Dict[str, Sequence[str]] = {
    "typing_tracking": (
        "key_count",
        "character_count",
        "backspace_count",
        "mean_interkey_latency",
        "typing_active_seconds",
    ),
    "switching_tracking": ("tab_switches", "window_switches"),
    "session_tracking": ("window_duration_s", "active_seconds", "idle_seconds"),
    "app_usage": ("app_name", "active_domain", "short_video_seconds"),
}

PRODUCTIVE_HINTS = ("docs", "notion", "figma", "github", "code", "cursor", "terminal", "stack")
COMMUNICATION_HINTS = ("slack", "teams", "gmail", "outlook", "mail", "discord", "meet", "zoom")
ENTERTAINMENT_HINTS = ("youtube", "netflix", "prime", "reels", "tiktok", "shorts", "instagram")
PERSONALIZATION_BASE_FEATURES = (
    "typing_speed_cpm",
    "error_rate",
    "mean_interkey_latency",
    "tab_switches_per_min",
    "fragmentation_index",
    "current_session_length_min",
    "idle_ratio",
    "seconds_in_entertainment_apps",
    "seconds_in_focus_apps",
    "short_video_seconds",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class MultiModalPipeline:
    def __init__(self):
        self._eye_models: Dict[str, ModelCEyeFatigue] = {}
        self._latest_eye_state: Dict[str, EyeFatigueResult] = {}

    def _get_eye_model(self, user_id: str) -> ModelCEyeFatigue:
        if user_id not in self._eye_models:
            self._eye_models[user_id] = ModelCEyeFatigue()
        return self._eye_models[user_id]

    def normalize_telemetry_payload(
        self,
        payload: MinuteTelemetryPayload,
    ) -> tuple[MinuteTelemetryPayload, List[str]]:
        """
        Ensures critical frontend telemetry groups are present and applies safe fallback values.
        """
        data = payload.model_dump(mode="python")
        provided_fields = set(payload.model_fields_set or [])
        missing_notes: List[str] = []

        for group_name, fields in TRACKING_REQUIREMENTS.items():
            missing = [name for name in fields if name not in provided_fields]
            if missing:
                note = f"{group_name} missing fields: {', '.join(missing)}"
                missing_notes.append(note)
                logger.warning("Telemetry fallback (%s): %s", group_name, ", ".join(missing))

        key_count = int(data.get("key_count") or 0)
        backspace_count = int(data.get("backspace_count") or 0)
        char_count = int(data.get("character_count") or 0)
        if char_count <= 0 and key_count > 0:
            data["character_count"] = max(0, key_count - backspace_count)

        duration = float(data.get("window_duration_s") or 60.0)
        active = float(data.get("active_seconds") or 0.0)
        idle = float(data.get("idle_seconds") or 0.0)
        if active <= 0 and idle > 0:
            data["active_seconds"] = max(duration - idle, 0.0)
        if idle <= 0 and active > 0:
            data["idle_seconds"] = max(duration - active, 0.0)

        if int(data.get("window_switches") or 0) <= 0 and int(data.get("tab_switches") or 0) > 0:
            data["window_switches"] = int(data["tab_switches"])
        if int(data.get("tab_switches") or 0) <= 0 and int(data.get("window_switches") or 0) > 0:
            data["tab_switches"] = int(data["window_switches"])

        if not data.get("app_name"):
            data["app_name"] = "browser"

        return MinuteTelemetryPayload(**data), missing_notes

    def ingest_eye_metrics(
        self,
        user_id: str,
        *,
        ear: float | None = None,
        blink_rate_per_min: float | None = None,
        closure_duration_s: float | None = None,
        frame_rate: float | None = None,
        timestamp: datetime | str | None = None,
        source: str = "manual",
    ) -> EyeFatigueResult:
        try:
            result = self._get_eye_model(user_id).update_from_metrics(
                ear=ear,
                blink_rate_per_min=blink_rate_per_min,
                closure_duration_s=closure_duration_s,
                frame_rate=frame_rate,
                timestamp=timestamp,
                source=source,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.exception("Eye pipeline failed for user=%s: %s", user_id, exc)
            result = EyeFatigueResult(
                timestamp=(timestamp.isoformat() if isinstance(timestamp, datetime) else datetime.now(UTC).isoformat()),
                source="fallback",
                warnings=["eye_pipeline_error"],
            )
        self._latest_eye_state[user_id] = result
        return result

    def latest_eye_state(self, user_id: str) -> EyeFatigueResult:
        state = self._latest_eye_state.get(user_id)
        if state is not None:
            return state
        fallback = EyeFatigueResult(
            timestamp=datetime.now(UTC).isoformat(),
            source="unavailable",
            warnings=["no_eye_signal_yet"],
        )
        self._latest_eye_state[user_id] = fallback
        return fallback

    def fuse_state(
        self,
        *,
        user_id: str,
        fatigue_score: float,
        load_score: float,
        model_a_reasons: List[str],
    ) -> FusionResult:
        eye = self.latest_eye_state(user_id)
        fused = fuse_scores(
            fatigue_score=fatigue_score,
            load_score=load_score,
            eye_fatigue_score=eye.eye_fatigue_score,
            drowsy_flag=eye.drowsy_flag,
        )
        fused.alerts = build_realtime_alerts(
            fatigue_score=fatigue_score,
            load_score=load_score,
            eye_fatigue_score=eye.eye_fatigue_score,
            drowsy_flag=eye.drowsy_flag,
            eye_closure_duration_s=eye.eye_closure_duration_s,
            blink_rate_per_min=eye.blink_rate_per_min,
            model_a_reasons=model_a_reasons,
        )
        return fused

    def analyze_app_usage(
        self,
        telemetry_points: Sequence[Dict[str, Any]],
        profile: OnboardingProfile,
    ) -> Dict[str, Any]:
        category_minutes: Dict[str, float] = {
            "productive": 0.0,
            "communication": 0.0,
            "entertainment": 0.0,
            "other": 0.0,
        }
        per_app: Dict[str, Dict[str, Any]] = {}
        total_switches = 0
        total_minutes = 0.0

        for point in telemetry_points:
            app = (point.get("active_domain") or point.get("app_name") or "unknown").lower()
            active_minutes = max(float(point.get("active_seconds", 0.0)) / 60.0, 0.0)
            switches = int(point.get("tab_switches", 0))
            category = self._classify_app(app=app, profile=profile)

            total_switches += switches
            total_minutes += active_minutes
            category_minutes[category] += active_minutes

            if app not in per_app:
                per_app[app] = {
                    "app": app,
                    "category": category,
                    "minutes": 0.0,
                    "switches": 0,
                    "impact_on_fatigue": 0.0,
                }

            row = per_app[app]
            row["minutes"] += active_minutes
            row["switches"] += switches

        switching_frequency = total_switches / max(total_minutes, 1.0)
        entertainment_ratio = category_minutes["entertainment"] / max(total_minutes, 1.0)
        impact_on_fatigue = _clamp(entertainment_ratio * 70.0 + switching_frequency * 12.0, 0.0, 100.0)

        for row in per_app.values():
            category_penalty = 22.0 if row["category"] == "entertainment" else 10.0 if row["category"] == "other" else 0.0
            row["impact_on_fatigue"] = round(
                _clamp(category_penalty + row["switches"] * 3.5 + row["minutes"] * 0.8, 0.0, 100.0),
                2,
            )
            row["minutes"] = round(float(row["minutes"]), 2)

        sorted_apps = sorted(per_app.values(), key=lambda item: item["minutes"], reverse=True)
        return {
            "time_spent_per_category_min": {name: round(value, 2) for name, value in category_minutes.items()},
            "switching_frequency_per_min": round(switching_frequency, 3),
            "impact_on_fatigue": round(impact_on_fatigue, 2),
            "apps": sorted_apps,
        }

    def extract_personalization_stats(self, features: Dict[str, float]) -> Dict[str, Dict[str, float]]:
        stats: Dict[str, Dict[str, float]] = {}
        for base_name in PERSONALIZATION_BASE_FEATURES:
            mean_key = f"rolling_mean_{base_name}"
            std_key = f"rolling_std_{base_name}"
            if mean_key in features and std_key in features:
                stats[base_name] = {
                    "rolling_mean": float(features.get(mean_key, 0.0)),
                    "rolling_std": float(features.get(std_key, 0.0)),
                }
        return stats

    def _classify_app(self, app: str, profile: OnboardingProfile) -> str:
        normalized = app.lower()

        if any(token in normalized for token in profile.focus_apps):
            return "productive"
        if any(token in normalized for token in profile.communication_apps):
            return "communication"
        if any(token in normalized for token in profile.entertainment_apps):
            return "entertainment"
        if any(token in normalized for token in profile.distraction_apps):
            return "entertainment"

        if any(token in normalized for token in COMMUNICATION_HINTS):
            return "communication"
        if any(token in normalized for token in ENTERTAINMENT_HINTS):
            return "entertainment"
        if any(token in normalized for token in PRODUCTIVE_HINTS):
            return "productive"
        return "other"


PIPELINE = MultiModalPipeline()
