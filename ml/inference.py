from __future__ import annotations

import json
import logging
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List, Tuple

from schema import ExplanationItem, ModelStatusResponse

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "realtime_cognitive_model.pkl"
MODEL_VERSION = "2.0.0"

CORE_FEATURES = [
    "mean_key_hold",
    "std_key_hold",
    "mean_interkey_latency",
    "std_interkey_latency",
    "typing_speed_cpm",
    "error_rate",
    "error_burstiness",
    "keystroke_activity_ratio",
    "tab_switches_per_min",
    "window_switches_per_min",
    "unique_domains",
    "avg_focus_duration_on_app",
    "fragmentation_index",
    "idle_seconds",
    "idle_ratio",
    "num_idle_bursts",
    "current_session_length_min",
    "num_breaks_last_hour",
    "time_since_last_break_min",
    "seconds_in_focus_apps",
    "seconds_in_communication_apps",
    "seconds_in_entertainment_apps",
    "entertainment_ratio",
    "comms_ratio",
    "short_video_seconds",
    "short_video_sessions",
    "time_of_day_sin",
    "time_of_day_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "hours_since_work_start",
    "baseline_fatigue_week",
    "baseline_stress_week",
    "deep_focus_capacity_min",
    "preferred_work_cycle_min",
    "focus_capacity_minutes",
    "break_style_score",
    "user_target_hours",
    "context_switch_sensitivity",
    "avg_sleep_hours",
    "last_night_sleep_hours",
    "focus_app_flag",
    "distraction_app_flag",
]

Z_FEATURE_BASES = [
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
]

FEATURE_COLUMNS = CORE_FEATURES + [f"z_{name}" for name in Z_FEATURE_BASES]

FEATURE_LABELS = {
    "typing_speed_cpm": "typing speed",
    "error_rate": "error rate",
    "mean_interkey_latency": "inter-key latency",
    "tab_switches_per_min": "tab switching",
    "fragmentation_index": "context fragmentation",
    "current_session_length_min": "session length",
    "idle_ratio": "idle ratio",
    "seconds_in_entertainment_apps": "entertainment usage",
    "seconds_in_focus_apps": "focus-app time",
    "short_video_seconds": "short-form video usage",
}

_predictor = None


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _import_model_backend():
    try:
        import lightgbm  # noqa: F401
        from lightgbm import LGBMClassifier
        return "lightgbm", LGBMClassifier
    except Exception:
        pass

    try:
        import xgboost  # noqa: F401
        from xgboost import XGBClassifier
        return "xgboost", XGBClassifier
    except Exception:
        pass

    from sklearn.ensemble import GradientBoostingClassifier

    return "sklearn_gradient_boosting", GradientBoostingClassifier


def _seed_training_rows() -> tuple[List[List[float]], List[int], List[int]]:
    rows: List[List[float]] = []
    fatigue_labels: List[int] = []
    load_labels: List[int] = []

    typing_options = [90, 140, 190, 250, 310]
    error_options = [0.02, 0.06, 0.12, 0.2]
    latency_options = [100, 150, 220, 320]
    switch_options = [0.3, 1.0, 2.0, 3.2]
    idle_options = [0.03, 0.1, 0.22]
    session_options = [25, 60, 110, 170]
    entertainment_options = [0, 25, 70]

    for typing in typing_options:
        for error in error_options:
            for latency in latency_options:
                for switches in switch_options:
                    for idle in idle_options:
                        for session in session_options:
                            for entertainment in entertainment_options:
                                row = {name: 0.0 for name in FEATURE_COLUMNS}
                                row.update(
                                    {
                                        "mean_key_hold": 95 + max(0, 220 - typing) * 0.12,
                                        "std_key_hold": 18 + error * 150,
                                        "mean_interkey_latency": latency,
                                        "std_interkey_latency": max(15, latency * 0.35),
                                        "typing_speed_cpm": float(typing),
                                        "error_rate": error,
                                        "error_burstiness": error * 12,
                                        "keystroke_activity_ratio": max(0.02, 0.75 - idle),
                                        "tab_switches_per_min": switches,
                                        "window_switches_per_min": switches * 0.7,
                                        "unique_domains": 1 + switches * 1.4,
                                        "avg_focus_duration_on_app": max(15, 260 - switches * 45),
                                        "fragmentation_index": switches / max(0.08, 0.75 - idle),
                                        "idle_seconds": idle * 300,
                                        "idle_ratio": idle,
                                        "num_idle_bursts": max(0, idle * 10),
                                        "current_session_length_min": float(session),
                                        "num_breaks_last_hour": 1.0 if idle > 0.12 else 0.0,
                                        "time_since_last_break_min": max(5, session * 0.8),
                                        "seconds_in_focus_apps": max(0, 240 - entertainment),
                                        "seconds_in_communication_apps": 25 + switches * 8,
                                        "seconds_in_entertainment_apps": float(entertainment),
                                        "entertainment_ratio": entertainment / 300.0,
                                        "comms_ratio": min(1.0, (25 + switches * 8) / 300.0),
                                        "short_video_seconds": float(entertainment if entertainment > 45 else 0),
                                        "short_video_sessions": 1.0 if entertainment > 45 else 0.0,
                                        "time_of_day_sin": 0.0,
                                        "time_of_day_cos": 1.0,
                                        "day_of_week_sin": 0.0,
                                        "day_of_week_cos": 1.0,
                                        "hours_since_work_start": max(0.0, session / 60.0),
                                        "baseline_fatigue_week": 35.0,
                                        "baseline_stress_week": 35.0,
                                        "deep_focus_capacity_min": 75.0,
                                        "preferred_work_cycle_min": 50.0,
                                        "context_switch_sensitivity": 50.0,
                                        "avg_sleep_hours": 7.5,
                                        "last_night_sleep_hours": 7.0,
                                        "focus_app_flag": 1.0 if entertainment < 30 else 0.0,
                                        "distraction_app_flag": 1.0 if entertainment >= 45 else 0.0,
                                        "z_typing_speed_cpm": (170 - typing) / 55.0,
                                        "z_error_rate": (error - 0.05) / 0.04,
                                        "z_mean_interkey_latency": (latency - 150) / 80.0,
                                        "z_tab_switches_per_min": (switches - 0.8) / 0.7,
                                        "z_fragmentation_index": ((switches / max(0.08, 0.75 - idle)) - 1.2) / 0.8,
                                        "z_current_session_length_min": (session - 70) / 40.0,
                                        "z_idle_ratio": (idle - 0.08) / 0.08,
                                        "z_seconds_in_entertainment_apps": (entertainment - 15) / 25.0,
                                        "z_seconds_in_focus_apps": (180 - max(0, 240 - entertainment)) / 45.0,
                                        "z_short_video_seconds": (max(0, entertainment - 45)) / 20.0,
                                    }
                                )

                                load_signal = (
                                    0.9 * row["z_tab_switches_per_min"]
                                    + 0.8 * row["z_fragmentation_index"]
                                    + 0.7 * row["z_error_rate"]
                                    + 0.5 * row["z_mean_interkey_latency"]
                                    + 0.3 * row["z_seconds_in_entertainment_apps"]
                                )
                                fatigue_signal = (
                                    0.8 * row["z_typing_speed_cpm"]
                                    + 0.75 * row["z_mean_interkey_latency"]
                                    + 0.7 * row["z_current_session_length_min"]
                                    + 0.55 * row["z_error_rate"]
                                    + 0.45 * (7.0 - row["last_night_sleep_hours"])
                                    + 0.3 * row["z_short_video_seconds"]
                                )

                                load_labels.append(1 if load_signal >= 1.1 else 0)
                                fatigue_labels.append(1 if fatigue_signal >= 1.25 else 0)
                                rows.append([row[name] for name in FEATURE_COLUMNS])

    return rows, fatigue_labels, load_labels


class RealtimePredictor:
    def __init__(self, load_model: Any, fatigue_model: Any, backend: str):
        self.load_model = load_model
        self.fatigue_model = fatigue_model
        self.backend = backend
        self.metadata = {
            "model_version": MODEL_VERSION,
            "backend": backend,
            "feature_count": len(FEATURE_COLUMNS),
        }
        self.importance_map = self._build_importance_map()

    def _build_importance_map(self) -> Dict[str, float]:
        load_importance = getattr(self.load_model, "feature_importances_", None)
        fatigue_importance = getattr(self.fatigue_model, "feature_importances_", None)
        if load_importance is None or fatigue_importance is None:
            return {name: 1.0 / len(FEATURE_COLUMNS) for name in FEATURE_COLUMNS}
        combined = {}
        for idx, name in enumerate(FEATURE_COLUMNS):
            combined[name] = float(load_importance[idx] + fatigue_importance[idx]) / 2.0
        return combined

    def predict(self, feature_dict: Dict[str, float], maturity: float) -> Dict[str, float]:
        row = [[float(feature_dict.get(name, 0.0)) for name in FEATURE_COLUMNS]]
        p_high = float(self.load_model.predict_proba(row)[0][1])
        p_fatigue = float(self.fatigue_model.predict_proba(row)[0][1])

        load_score = _clamp((p_high * 100.0) + max(0.0, feature_dict.get("z_tab_switches_per_min", 0.0) * 5), 0.0, 100.0)
        fatigue_score = _clamp((p_fatigue * 100.0) + max(0.0, feature_dict.get("z_current_session_length_min", 0.0) * 4), 0.0, 100.0)
        raw_confidence = max(p_high, p_fatigue)
        confidence = _clamp(0.35 + raw_confidence * 0.55 + maturity * 0.1, 0.2, 0.99)

        return {
            "p_high_load": round(p_high, 6),
            "p_fatigue": round(p_fatigue, 6),
            "load_score": round(load_score, 2),
            "fatigue_score": round(fatigue_score, 2),
            "confidence": round(confidence, 4),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as handle:
            pickle.dump(
                {
                    "load_model": self.load_model,
                    "fatigue_model": self.fatigue_model,
                    "backend": self.backend,
                    "metadata": self.metadata,
                },
                handle,
            )

    @classmethod
    def load(cls, path: Path) -> "RealtimePredictor":
        with open(path, "rb") as handle:
            artifact = pickle.load(handle)
        predictor = cls(
            load_model=artifact["load_model"],
            fatigue_model=artifact["fatigue_model"],
            backend=artifact["backend"],
        )
        predictor.metadata = artifact.get("metadata", predictor.metadata)
        return predictor


def _train_bootstrap_predictor() -> RealtimePredictor:
    backend_name, model_cls = _import_model_backend()
    rows, fatigue_labels, load_labels = _seed_training_rows()
    logger.info("Training bootstrap cognitive model with backend=%s and %s rows", backend_name, len(rows))

    if backend_name == "lightgbm":
        load_model = model_cls(n_estimators=160, learning_rate=0.05, max_depth=5, class_weight="balanced", random_state=42)
        fatigue_model = model_cls(n_estimators=160, learning_rate=0.05, max_depth=5, class_weight="balanced", random_state=43)
    elif backend_name == "xgboost":
        load_model = model_cls(
            n_estimators=180,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
        )
        fatigue_model = model_cls(
            n_estimators=180,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=43,
        )
    else:
        load_model = model_cls(random_state=42)
        fatigue_model = model_cls(random_state=43)

    load_model.fit(rows, load_labels)
    fatigue_model.fit(rows, fatigue_labels)

    predictor = RealtimePredictor(load_model=load_model, fatigue_model=fatigue_model, backend=backend_name)
    predictor.save(MODEL_PATH)
    return predictor


def get_predictor() -> RealtimePredictor:
    global _predictor
    if _predictor is not None:
        return _predictor
    if MODEL_PATH.exists():
        try:
            _predictor = RealtimePredictor.load(MODEL_PATH)
            if _predictor.metadata.get("feature_count") != len(FEATURE_COLUMNS):
                _predictor = _train_bootstrap_predictor()
            return _predictor
        except Exception as exc:
            logger.warning("Failed to load saved model: %s", exc)
    _predictor = _train_bootstrap_predictor()
    return _predictor


def predict_scores(feature_dict: Dict[str, float], maturity: float) -> Dict[str, float]:
    predictor = get_predictor()
    return predictor.predict(feature_dict, maturity=maturity)


def explain_prediction(feature_dict: Dict[str, float], scores: Dict[str, float], max_items: int = 5) -> List[ExplanationItem]:
    predictor = get_predictor()
    candidates: List[Tuple[str, float, str]] = []
    for base_name in Z_FEATURE_BASES:
        z_name = f"z_{base_name}"
        z_value = float(feature_dict.get(z_name, 0.0))
        if abs(z_value) < 0.35:
            continue
        importance = predictor.importance_map.get(z_name, predictor.importance_map.get(base_name, 0.0))
        impact = abs(z_value) * (0.7 + importance * 4)
        label = FEATURE_LABELS.get(base_name, base_name.replace("_", " "))
        direction = "up" if z_value > 0 else "down"

        if base_name == "typing_speed_cpm":
            reason = "typing speed down vs your normal" if z_value > 0 else "typing speed stronger than usual"
        elif base_name == "error_rate":
            reason = "error rate is above your normal" if z_value > 0 else "error rate is below your normal"
        elif base_name == "mean_interkey_latency":
            reason = "keystrokes are slower than your normal" if z_value > 0 else "keystroke latency is faster than your normal"
        elif base_name == "tab_switches_per_min":
            reason = "tab switching is higher than usual" if z_value > 0 else "tab switching is calmer than usual"
        elif base_name == "fragmentation_index":
            reason = "context fragmentation is elevated" if z_value > 0 else "context fragmentation is lower than usual"
        elif base_name == "current_session_length_min":
            reason = "you have been working a long stretch without a real break" if z_value > 0 else "session length is still within your normal range"
        elif base_name == "seconds_in_entertainment_apps":
            reason = "entertainment usage is elevated during active work time" if z_value > 0 else "entertainment usage is lower than usual"
        elif base_name == "seconds_in_focus_apps":
            reason = "focus-app time is below your normal" if z_value > 0 else "focus-app time is higher than usual"
        elif base_name == "short_video_seconds":
            reason = "short-form video usage is unusually high" if z_value > 0 else "short-form video usage is quiet"
        else:
            reason = f"{label} moved {'up' if z_value > 0 else 'down'} vs your normal"

        candidates.append((base_name, impact, reason))

    if not candidates:
        candidates.append(("baseline", 0.4, "Signals are close to your normal range right now."))

    candidates.sort(key=lambda item: item[1], reverse=True)
    return [
        ExplanationItem(feature=name, direction="up", impact=round(impact, 3), reason=reason)
        for name, impact, reason in candidates[:max_items]
    ]


def get_status() -> ModelStatusResponse:
    predictor = get_predictor()
    return ModelStatusResponse(
        status="ready",
        model_type="dual_binary_classifier",
        model_version=predictor.metadata["model_version"],
        feature_count=predictor.metadata["feature_count"],
        backend=predictor.metadata["backend"],
        explanation_mode="importance_plus_personal_zscore",
    )


try:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/status", response_model=ModelStatusResponse)
    def ml_status():
        return get_status()

    @router.post("/predict")
    def ml_predict_endpoint(payload: Dict[str, Any]):
        maturity = float(payload.pop("model_maturity", 0.0))
        scores = predict_scores(payload, maturity)
        return scores

except Exception:
    router = None
