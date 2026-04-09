from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from data.ingestion import group_events_by_user
from data.schema import FeatureWindow, RawEvent, WindowConfig
from features.extractor import FEATURE_KEYS_FOR_ZSCORE, FeatureRuntimeContext, compute_window_features
from features.personalization import RollingBaseline
from features.windowing import iter_sliding_windows


@dataclass
class UserFeatureState:
    context: FeatureRuntimeContext = field(default_factory=FeatureRuntimeContext)
    baseline: RollingBaseline = field(default_factory=RollingBaseline)


class RealTimeFeaturePipeline:
    """
    End-to-end event -> window -> features pipeline for Model A.

    Locked design:
    - 5-minute sliding window
    - 1-minute stride
    - rolling personalization via z-scores
    """

    def __init__(self, window_config: WindowConfig | None = None, baseline_history_windows: int = 16 * 60):
        self.window_config = window_config or WindowConfig()
        self._states: Dict[str, UserFeatureState] = defaultdict(
            lambda: UserFeatureState(baseline=RollingBaseline(max_windows=baseline_history_windows))
        )

    def reset_user(self, user_id: str) -> None:
        self._states.pop(user_id, None)

    def build_feature_windows(
        self,
        events: Iterable[RawEvent],
        include_partial: bool = False,
        reset_user_state: bool = False,
    ) -> List[FeatureWindow]:
        grouped = group_events_by_user(events)
        output: List[FeatureWindow] = []
        for user_id, user_events in grouped.items():
            output.extend(
                self.build_feature_windows_for_user(
                    user_id=user_id,
                    events=user_events,
                    include_partial=include_partial,
                    reset_state=reset_user_state,
                )
            )
        output.sort(key=lambda row: (row.user_id, row.window_end))
        return output

    def build_feature_windows_for_user(
        self,
        user_id: str,
        events: List[RawEvent],
        include_partial: bool = False,
        reset_state: bool = False,
    ) -> List[FeatureWindow]:
        if reset_state:
            self.reset_user(user_id)
        state = self._states[user_id]
        records: List[FeatureWindow] = []

        for window in iter_sliding_windows(
            user_id=user_id,
            events=events,
            config=self.window_config,
            include_partial=include_partial,
        ):
            raw_features = compute_window_features(window=window, context=state.context)
            self._inject_runtime_aliases(raw_features, window_seconds=float(window.window_size_seconds))
            personalized = self._apply_personalization(state.baseline, raw_features)
            records.append(
                FeatureWindow(
                    user_id=user_id,
                    window_start=window.start,
                    window_end=window.end,
                    window_size_seconds=window.window_size_seconds,
                    step_seconds=window.step_seconds,
                    source_event_count=len(window.events),
                    feature_vector=personalized,
                )
            )
        return records

    def _apply_personalization(self, baseline: RollingBaseline, raw_features: Dict[str, float]) -> Dict[str, float]:
        features_for_baseline = {key: raw_features[key] for key in FEATURE_KEYS_FOR_ZSCORE if key in raw_features}
        baseline_features = baseline.snapshot(features_for_baseline)
        baseline.update(features_for_baseline)

        combined = dict(raw_features)
        combined.update(baseline_features)

        # Compatibility aliases for legacy inference module z-features.
        combined["z_typing_speed_cpm"] = combined.get("z_typing_speed", 0.0)
        combined["rolling_mean_typing_speed_cpm"] = combined.get("rolling_mean_typing_speed", 0.0)
        combined["rolling_std_typing_speed_cpm"] = combined.get("rolling_std_typing_speed", 0.0)
        combined["z_tab_switches_per_min"] = combined.get("z_switches_per_minute", 0.0)
        combined["z_current_session_length_min"] = combined.get("z_session_duration", 0.0)
        combined["z_seconds_in_entertainment_apps"] = combined.get("z_time_entertainment_category", 0.0)
        combined["z_seconds_in_focus_apps"] = combined.get("z_time_focus_category", 0.0)

        return combined

    def _inject_runtime_aliases(self, features: Dict[str, float], window_seconds: float) -> None:
        features.setdefault("window_switches_per_min", features.get("switches_per_minute", 0.0))
        features.setdefault(
            "avg_focus_duration_on_app",
            features.get("time_focus_category", 0.0) / max(features.get("unique_apps_count", 0.0), 1.0),
        )
        features.setdefault("idle_seconds", features.get("idle_ratio", 0.0) * window_seconds)
        features.setdefault("num_idle_bursts", 0.0)
        features.setdefault("comms_ratio", features.get("time_communication_category", 0.0) / max(window_seconds, 1.0))
        features.setdefault("short_video_seconds", 0.0)
        features.setdefault("short_video_sessions", 0.0)
