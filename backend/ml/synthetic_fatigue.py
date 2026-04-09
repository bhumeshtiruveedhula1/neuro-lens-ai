from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score
from xgboost import XGBClassifier, XGBRegressor


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "model.json"
DEFAULT_CLASSIFIER_PATH = Path(__file__).resolve().parent / "fatigue_classifier.json"
DEFAULT_REGRESSOR_PATH = Path(__file__).resolve().parent / "fatigue_regressor.json"

FEATURE_COLUMNS = [
    "typing_speed",
    "inter_key_latency_mean",
    "inter_key_latency_std",
    "hold_time_mean",
    "error_rate",
    "error_burstiness",
    "switches_per_minute",
    "app_usage_per_minute",
    "idle_ratio",
    "session_duration_min",
    "time_since_last_break",
    "cumulative_work_time",
    "fatigue_accumulation_index",
    "typing_speed_trend",
    "error_rate_trend",
    "switching_trend",
    "hour_of_day_sin",
    "hour_of_day_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "z_typing_speed",
    "z_inter_key_latency_mean",
    "z_error_rate",
    "z_switches_per_minute",
    "z_idle_ratio",
    "z_session_duration_min",
    "z_fatigue_accumulation_index",
]

BASE_FEATURES_FOR_Z = [
    "typing_speed",
    "inter_key_latency_mean",
    "error_rate",
    "switches_per_minute",
    "idle_ratio",
    "session_duration_min",
    "fatigue_accumulation_index",
]

REASON_LABELS = {
    "typing_speed": "typing speed is below your normal",
    "inter_key_latency_mean": "keystrokes are slower than your normal",
    "inter_key_latency_std": "typing rhythm is more erratic than usual",
    "hold_time_mean": "key hold time is longer than usual",
    "error_rate": "error rate is elevated",
    "error_burstiness": "errors are clustering in bursts",
    "switches_per_minute": "context switching is unusually high",
    "app_usage_per_minute": "app activity is unusually dense",
    "idle_ratio": "idle time is elevated",
    "session_duration_min": "the current session has run long",
    "time_since_last_break": "it has been a while since the last break",
    "cumulative_work_time": "work has accumulated for a long stretch",
    "fatigue_accumulation_index": "fatigue accumulation is high",
    "typing_speed_trend": "typing speed is trending downward",
    "error_rate_trend": "errors are trending upward",
    "switching_trend": "switching is trending upward",
    "z_typing_speed": "typing speed dropped versus baseline",
    "z_inter_key_latency_mean": "latency rose versus baseline",
    "z_error_rate": "errors rose versus baseline",
    "z_switches_per_minute": "switching rose versus baseline",
    "z_idle_ratio": "idle ratio rose versus baseline",
    "z_session_duration_min": "session length rose versus baseline",
    "z_fatigue_accumulation_index": "fatigue accumulation rose versus baseline",
}


@dataclass
class SyntheticConfig:
    users: int = 160
    sessions_per_user: int = 6
    windows_per_session: int = 24
    window_minutes: int = 5
    seed: int = 42


@dataclass
class TrainingArtifacts:
    dataset_path: str
    manifest_path: str
    report_path: str
    classifier_model_path: str
    regressor_model_path: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _cyclic(value: float, period: float) -> Tuple[float, float]:
    angle = 2.0 * math.pi * (value / period)
    return math.sin(angle), math.cos(angle)


def _compute_trend(values: pd.Series, window: int = 4) -> pd.Series:
    trend = values.diff().rolling(window=window, min_periods=2).mean()
    return trend.fillna(0.0)


def generate_synthetic_fatigue_dataset(config: SyntheticConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    base_start = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    rows: List[Dict[str, float | int | str]] = []

    for user_index in range(config.users):
        user_id = f"sim_user_{user_index + 1:03d}"
        chronotype_shift = float(rng.normal(0.0, 1.0))
        typing_baseline = float(rng.normal(235.0, 18.0))
        latency_baseline = float(rng.normal(118.0, 10.0))
        hold_baseline = float(rng.normal(86.0, 7.0))
        error_baseline = float(_clamp(rng.normal(0.028, 0.008), 0.01, 0.07))
        switch_baseline = float(_clamp(rng.normal(0.75, 0.18), 0.25, 1.5))
        app_usage_baseline = float(_clamp(rng.normal(7.5, 1.6), 3.0, 12.0))
        idle_baseline = float(_clamp(rng.normal(0.06, 0.02), 0.01, 0.15))
        resilience = float(_clamp(rng.normal(1.0, 0.12), 0.75, 1.25))

        cumulative_work_minutes = 0.0
        current_day = base_start + timedelta(days=user_index % 5)

        for session_index in range(config.sessions_per_user):
            day_offset = session_index // 2
            session_day = current_day + timedelta(days=day_offset)
            session_start_hour = float(_clamp(rng.normal(9.5 + chronotype_shift, 2.1), 6.5, 21.0))
            session_start = session_day.replace(
                hour=int(session_start_hour),
                minute=int((session_start_hour % 1.0) * 60.0),
                second=0,
                microsecond=0,
            )
            prior_break_minutes = float(_clamp(rng.normal(35.0, 12.0), 8.0, 80.0))
            time_since_last_break = prior_break_minutes
            session_duration = 0.0
            fatigue_accumulation = float(_clamp(rng.normal(8.0, 4.0), 0.0, 20.0))
            circadian_penalty = max(0.0, abs((session_start_hour - 14.0) / 9.0) - 0.35)
            sleep_debt = float(_clamp(rng.normal(0.0, 0.8), -1.0, 2.5))

            for window_index in range(config.windows_per_session):
                timestamp = session_start + timedelta(minutes=window_index * config.window_minutes)
                phase_progress = window_index / max(config.windows_per_session - 1, 1)

                fresh_component = max(0.0, 0.22 - phase_progress * 0.18)
                normal_component = max(0.0, 0.35 - abs(phase_progress - 0.28) * 0.8)
                high_load_component = max(0.0, 0.55 - abs(phase_progress - 0.58) * 1.2)
                fatigue_component = max(0.0, (phase_progress - 0.45) * 1.35)

                work_intensity = float(_clamp(
                    0.35 * normal_component
                    + 0.85 * high_load_component
                    + 1.1 * fatigue_component
                    + rng.normal(0.0, 0.05),
                    0.0,
                    1.6,
                ))
                fatigue_accumulation = float(_clamp(
                    fatigue_accumulation
                    + (1.8 + 4.5 * high_load_component + 7.5 * fatigue_component) / resilience
                    - fresh_component * 1.4
                    + sleep_debt * 0.35
                    + rng.normal(0.0, 0.6),
                    0.0,
                    100.0,
                ))

                micro_break = bool(
                    fatigue_component > 0.55 and rng.random() < 0.18
                    or high_load_component > 0.45 and rng.random() < 0.06
                )
                if micro_break:
                    recovered = float(_clamp(rng.normal(14.0, 4.0), 6.0, 24.0))
                    time_since_last_break = max(2.0, time_since_last_break - recovered)
                    fatigue_accumulation = max(0.0, fatigue_accumulation - recovered * 0.9)
                else:
                    time_since_last_break += config.window_minutes

                session_duration += config.window_minutes
                cumulative_work_minutes += config.window_minutes

                latent_fatigue = (
                    6.5
                    + 58.0 * fatigue_component
                    + 26.0 * high_load_component
                    + 0.22 * fatigue_accumulation
                    + 0.10 * session_duration
                    + 0.035 * cumulative_work_minutes
                    + 10.0 * circadian_penalty
                    + 4.5 * max(sleep_debt, 0.0)
                    + rng.normal(0.0, 4.2)
                )
                fatigue_score = float(_clamp(latent_fatigue, 0.0, 100.0))

                typing_speed = float(_clamp(
                    typing_baseline
                    - 0.72 * fatigue_score
                    - 10.5 * work_intensity
                    + 5.5 * fresh_component
                    + rng.normal(0.0, 10.0),
                    65.0,
                    340.0,
                ))
                inter_key_latency_mean = float(_clamp(
                    latency_baseline
                    + 1.12 * fatigue_score
                    + 11.5 * work_intensity
                    + rng.normal(0.0, 8.0),
                    65.0,
                    320.0,
                ))
                inter_key_latency_std = float(_clamp(
                    16.0
                    + fatigue_score * 0.28
                    + work_intensity * 5.5
                    + rng.normal(0.0, 3.5),
                    6.0,
                    85.0,
                ))
                hold_time_mean = float(_clamp(
                    hold_baseline
                    + fatigue_score * 0.36
                    + work_intensity * 3.8
                    + rng.normal(0.0, 3.5),
                    45.0,
                    180.0,
                ))
                error_rate = float(_clamp(
                    error_baseline
                    + fatigue_score * 0.0019
                    + work_intensity * 0.014
                    + rng.normal(0.0, 0.008),
                    0.005,
                    0.42,
                ))
                error_burstiness = float(_clamp(
                    0.18
                    + fatigue_score * 0.016
                    + error_rate * 16.0
                    + rng.normal(0.0, 0.35),
                    0.0,
                    12.0,
                ))
                switches_per_minute = float(_clamp(
                    switch_baseline
                    + fatigue_score * 0.0105
                    + work_intensity * 0.40
                    + rng.normal(0.0, 0.12),
                    0.05,
                    6.0,
                ))
                app_usage_per_minute = float(_clamp(
                    app_usage_baseline
                    + work_intensity * 2.2
                    + fatigue_score * 0.018
                    + rng.normal(0.0, 0.75),
                    1.5,
                    22.0,
                ))
                idle_ratio = float(_clamp(
                    idle_baseline
                    + fatigue_score * 0.0034
                    + max(0.0, fatigue_component - 0.35) * 0.11
                    + rng.normal(0.0, 0.015),
                    0.0,
                    0.62,
                ))

                hour_value = float(timestamp.hour) + float(timestamp.minute) / 60.0
                hour_sin, hour_cos = _cyclic(hour_value, 24.0)
                dow_sin, dow_cos = _cyclic(float(timestamp.weekday()), 7.0)

                rows.append(
                    {
                        "user_id": user_id,
                        "timestamp": timestamp.isoformat(),
                        "session_id": f"{user_id}_session_{session_index + 1}",
                        "typing_speed": typing_speed,
                        "inter_key_latency_mean": inter_key_latency_mean,
                        "inter_key_latency_std": inter_key_latency_std,
                        "hold_time_mean": hold_time_mean,
                        "error_rate": error_rate,
                        "error_burstiness": error_burstiness,
                        "switches_per_minute": switches_per_minute,
                        "app_usage_per_minute": app_usage_per_minute,
                        "idle_ratio": idle_ratio,
                        "session_duration_min": session_duration,
                        "time_since_last_break": time_since_last_break,
                        "cumulative_work_time": cumulative_work_minutes,
                        "fatigue_accumulation_index": fatigue_accumulation,
                        "hour_of_day_sin": hour_sin,
                        "hour_of_day_cos": hour_cos,
                        "day_of_week_sin": dow_sin,
                        "day_of_week_cos": dow_cos,
                        "latent_fatigue_component": fatigue_component,
                        "work_intensity": work_intensity,
                        "fatigue_score": fatigue_score,
                    }
                )

            cumulative_work_minutes = max(0.0, cumulative_work_minutes - float(_clamp(rng.normal(70.0, 20.0), 30.0, 120.0)))

    dataset = pd.DataFrame(rows).sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    return dataset


def engineer_features(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    for column, trend_name in [
        ("typing_speed", "typing_speed_trend"),
        ("error_rate", "error_rate_trend"),
        ("switches_per_minute", "switching_trend"),
    ]:
        df[trend_name] = (
            df.groupby("user_id", sort=False)[column]
            .transform(lambda series: _compute_trend(series))
        )

    for base_column in BASE_FEATURES_FOR_Z:
        history_mean = (
            df.groupby("user_id", sort=False)[base_column]
            .transform(lambda series: series.shift(1).rolling(window=24, min_periods=5).mean())
        )
        history_std = (
            df.groupby("user_id", sort=False)[base_column]
            .transform(lambda series: series.shift(1).rolling(window=24, min_periods=5).std())
        )
        z_name = f"z_{base_column}"
        df[z_name] = (
            (df[base_column] - history_mean) / history_std.replace(0.0, np.nan)
        ).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    fatigue_probability = 1.0 / (1.0 + np.exp(-(df["fatigue_score"] - 58.0) / 7.5))
    fatigue_probability = np.clip(fatigue_probability * 0.88 + 0.06, 0.02, 0.98)
    rng = np.random.default_rng(2026)
    df["fatigue_label"] = (rng.random(len(df)) < fatigue_probability).astype(int)
    df["fatigue_probability_target"] = fatigue_probability

    return df


def split_user_level(df: pd.DataFrame, test_fraction: float = 0.2, seed: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
    users = np.array(sorted(df["user_id"].unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(users)
    test_count = max(1, int(round(len(users) * test_fraction)))
    test_users = set(users[:test_count])
    train_df = df[~df["user_id"].isin(test_users)].copy()
    test_df = df[df["user_id"].isin(test_users)].copy()
    return train_df, test_df


def train_models(
    train_df: pd.DataFrame,
    feature_columns: Iterable[str] = FEATURE_COLUMNS,
    seed: int = 42,
) -> Tuple[XGBClassifier, XGBRegressor]:
    feature_columns = list(feature_columns)
    X_train = train_df[feature_columns].to_numpy()
    y_class = train_df["fatigue_label"].to_numpy()
    y_score = train_df["fatigue_score"].to_numpy()

    positives = int(np.sum(y_class == 1))
    negatives = int(np.sum(y_class == 0))
    scale_pos_weight = float(negatives / max(positives, 1))

    classifier = XGBClassifier(
        n_estimators=180,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.92,
        colsample_bytree=0.92,
        min_child_weight=4,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=seed,
        n_jobs=4,
        scale_pos_weight=scale_pos_weight,
    )
    regressor = XGBRegressor(
        n_estimators=220,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.92,
        colsample_bytree=0.92,
        min_child_weight=4,
        reg_lambda=1.0,
        objective="reg:squarederror",
        eval_metric="rmse",
        tree_method="hist",
        random_state=seed + 1,
        n_jobs=4,
    )

    classifier.fit(X_train, y_class)
    regressor.fit(X_train, y_score)
    return classifier, regressor


def evaluate_models(
    classifier: XGBClassifier,
    regressor: XGBRegressor,
    test_df: pd.DataFrame,
    feature_columns: Iterable[str] = FEATURE_COLUMNS,
) -> Dict[str, object]:
    feature_columns = list(feature_columns)
    X_test = test_df[feature_columns].to_numpy()
    y_class = test_df["fatigue_label"].to_numpy()
    y_score = test_df["fatigue_score"].to_numpy()

    prob = classifier.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    score_pred = np.clip(regressor.predict(X_test), 0.0, 100.0)

    mae = float(np.mean(np.abs(score_pred - y_score)))
    rmse = float(np.sqrt(np.mean((score_pred - y_score) ** 2)))
    feature_importance = sorted(
        (
            {"feature": feature_columns[idx], "importance": round(float(value), 6)}
            for idx, value in enumerate(classifier.feature_importances_)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )

    return {
        "auc": round(float(roc_auc_score(y_class, prob)), 6),
        "f1": round(float(f1_score(y_class, pred, zero_division=0)), 6),
        "confusion_matrix": confusion_matrix(y_class, pred, labels=[0, 1]).astype(int).tolist(),
        "regression_mae": round(mae, 6),
        "regression_rmse": round(rmse, 6),
        "feature_importance": feature_importance[:12],
    }


class SyntheticFatiguePredictor:
    def __init__(
        self,
        classifier: XGBClassifier,
        regressor: XGBRegressor,
        manifest: Dict[str, object],
    ) -> None:
        self.classifier = classifier
        self.regressor = regressor
        self.manifest = manifest
        self.feature_columns = list(manifest["feature_columns"])
        self.importance_map = {
            item["feature"]: float(item["importance"])
            for item in manifest.get("feature_importance", [])
        }
        self.feature_stats = manifest.get("feature_stats", {})

    def predict_fatigue(self, input_features: Dict[str, float]) -> Dict[str, object]:
        row = [float(input_features.get(name, 0.0)) for name in self.feature_columns]
        probability = float(self.classifier.predict_proba([row])[0][1])
        fatigue_score = float(np.clip(self.regressor.predict([row])[0], 0.0, 100.0))
        fatigue_label = int(probability >= 0.5 or fatigue_score >= 60.0)

        reason_scores: List[Tuple[str, float]] = []
        for feature_name in self.feature_columns:
            value = float(input_features.get(feature_name, 0.0))
            importance = self.importance_map.get(feature_name, 0.0)
            stats = self.feature_stats.get(feature_name, {})
            mean_value = float(stats.get("mean", 0.0))
            std_value = float(stats.get("std", 1.0))
            if feature_name.startswith("z_"):
                magnitude = abs(value)
            elif "trend" in feature_name:
                magnitude = abs(value) / max(std_value, 1e-6)
            else:
                magnitude = abs(value - mean_value) / max(std_value, 1e-6)
            reason_scores.append((feature_name, magnitude * max(importance, 0.01)))

        reason_scores.sort(key=lambda item: item[1], reverse=True)
        top_reasons = [REASON_LABELS.get(name, name.replace("_", " ")) for name, _ in reason_scores[:3]]

        return {
            "fatigue_score": round(fatigue_score, 2),
            "fatigue_label": fatigue_label,
            "top_3_reasons": top_reasons,
            "fatigue_probability": round(probability, 6),
        }

    @classmethod
    def load(cls, manifest_path: str | Path) -> "SyntheticFatiguePredictor":
        manifest_path = Path(manifest_path)
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        else:
            manifest = {
                "feature_columns": FEATURE_COLUMNS,
                "classifier_model_path": str(DEFAULT_CLASSIFIER_PATH),
                "regressor_model_path": str(DEFAULT_REGRESSOR_PATH),
                "feature_importance": [{"feature": name, "importance": 1.0 / len(FEATURE_COLUMNS)} for name in FEATURE_COLUMNS],
                "feature_stats": {name: {"mean": 0.0, "std": 1.0} for name in FEATURE_COLUMNS},
            }

        classifier = XGBClassifier()
        classifier.load_model(manifest["classifier_model_path"])
        regressor = XGBRegressor()
        regressor.load_model(manifest["regressor_model_path"])
        return cls(classifier=classifier, regressor=regressor, manifest=manifest)


def save_artifacts(
    dataset: pd.DataFrame,
    classifier: XGBClassifier,
    regressor: XGBRegressor,
    evaluation: Dict[str, object],
    output_dir: str | Path,
) -> TrainingArtifacts:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    models_dir = output_dir / "models"
    reports_dir = output_dir / "evaluation"
    data_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = data_dir / "synthetic_dataset.csv"
    classifier_path = models_dir / "fatigue_classifier.json"
    regressor_path = models_dir / "fatigue_regressor.json"
    manifest_path = models_dir / "model.json"
    report_path = reports_dir / "training_report.json"

    dataset.to_csv(dataset_path, index=False)
    classifier.save_model(classifier_path)
    regressor.save_model(regressor_path)

    feature_stats = {
        name: {
            "mean": round(float(dataset[name].mean()), 6),
            "std": round(float(dataset[name].std() if dataset[name].std() > 1e-9 else 1.0), 6),
        }
        for name in FEATURE_COLUMNS
    }

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "model_type": "synthetic_bootstrap_dual_xgboost",
        "feature_columns": FEATURE_COLUMNS,
        "classifier_model_path": str(classifier_path),
        "regressor_model_path": str(regressor_path),
        "feature_importance": evaluation["feature_importance"],
        "feature_stats": feature_stats,
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_shape": {
            "rows": int(dataset.shape[0]),
            "columns": int(dataset.shape[1]),
        },
        "feature_list": FEATURE_COLUMNS,
        "normalization_strategy": "Per-user rolling z-scores on primary behavioral and cognitive features; raw features kept in natural units for explainability.",
        "metrics": {
            "auc": evaluation["auc"],
            "f1": evaluation["f1"],
            "confusion_matrix": evaluation["confusion_matrix"],
            "regression_mae": evaluation["regression_mae"],
            "regression_rmse": evaluation["regression_rmse"],
        },
        "feature_importance": evaluation["feature_importance"],
        "disclaimer": "Synthetic prototype for hackathon demonstration only. Not medical advice or validated clinical fatigue detection.",
        "artifacts": {
            "synthetic_dataset_csv": str(dataset_path),
            "model_json": str(manifest_path),
            "training_report_json": str(report_path),
            "classifier_model_json": str(classifier_path),
            "regressor_model_json": str(regressor_path),
        },
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    return TrainingArtifacts(
        dataset_path=str(dataset_path),
        manifest_path=str(manifest_path),
        report_path=str(report_path),
        classifier_model_path=str(classifier_path),
        regressor_model_path=str(regressor_path),
    )


def predict_fatigue(
    input_features: Dict[str, float],
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> Dict[str, object]:
    predictor = SyntheticFatiguePredictor.load(manifest_path)
    return predictor.predict_fatigue(input_features)
