"""
NeuroLens AI -- ML Pipeline
============================
Research-grounded fatigue detection model for small datasets (10-100 users).

Model selection rationale (from Prompt 2 / literature):
  - Random Forest: "highest mean accuracy ~91.8%" in driver fatigue paper;
    robust to irrelevant features; strong baseline for keystroke/smartphone data
  - SVM (RBF kernel): common in keystroke stress papers; strong with small N
  - Logistic Regression: L2 regularised; data-efficient; interpretable
  - k-NN: "reached ~84% accuracy" in keystroke-based stress detection

Strategy:
  1. Train all four models (no extra cost -- they're all fast)
  2. Select best by cross-validated F1-macro (per-user CV when possible)
  3. Export the winner as the production model

Evaluation targets (from Prompt 4):
  - Subject-dependent F1 >= 0.70 is "good" (our primary target)
  - AUC >= 0.80 (ROC one-vs-rest)
  - Report per-class precision/recall -- fatigued class is most important

Preprocessing:
  - StandardScaler: matches research convention for SVM and LR
  - RF and k-NN are scale-invariant, but scaling helps k-NN distance metric
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ml.features import get_full_feature_names, get_minimal_feature_names

# ── Lazy sklearn imports (avoid import error in environments without sklearn) ──

def _check_sklearn():
    try:
        import sklearn
        return True
    except ImportError:
        return False

SKLEARN_AVAILABLE = _check_sklearn()


# ── Label mappings ─────────────────────────────────────────────────────────────
LABEL_NAMES = ["NORMAL", "ELEVATED", "HIGH"]
LABEL_TO_INT = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2}
INT_TO_LABEL = {0: "NORMAL", 1: "ELEVATED", 2: "HIGH"}


# ── Model configs ──────────────────────────────────────────────────────────────
# Parameters tuned for small datasets (Prompt 2 recommendations)
MODEL_CONFIGS = {
    "random_forest": {
        "class": "RandomForestClassifier",
        "module": "sklearn.ensemble",
        "params": {
            "n_estimators": 200,      # enough trees; small dataset, fast
            "max_depth": 5,           # prevent overfitting with small N
            "min_samples_leaf": 3,    # regularisation for small datasets
            "class_weight": "balanced",  # handles class imbalance
            "random_state": 42,
            "n_jobs": -1,
        },
    },
    "svm": {
        "class": "SVC",
        "module": "sklearn.svm",
        "params": {
            "kernel": "rbf",
            "C": 1.0,
            "gamma": "scale",
            "class_weight": "balanced",
            "probability": True,    # needed for AUC
            "random_state": 42,
        },
    },
    "logistic_regression": {
        "class": "LogisticRegression",
        "module": "sklearn.linear_model",
        "params": {
            "C": 0.5,               # stronger L2 regularisation for small N
            "max_iter": 1000,
            "class_weight": "balanced",
            "solver": "lbfgs",
            "random_state": 42,
        },
    },
    "knn": {
        "class": "KNeighborsClassifier",
        "module": "sklearn.neighbors",
        "params": {
            "n_neighbors": 5,       # tested as top performer in keystroke stress paper
            "weights": "distance",
            "metric": "euclidean",
            "n_jobs": -1,
        },
    },
}


def _import_class(module: str, classname: str):
    import importlib
    mod = importlib.import_module(module)
    return getattr(mod, classname)


# ── Preprocessing ──────────────────────────────────────────────────────────────

class FatiguePreprocessor:
    """
    StandardScaler wrapper. Fit on training data, apply to inference.
    Stored alongside the model in the artifact.
    """
    def __init__(self):
        from sklearn.preprocessing import StandardScaler
        self.scaler = StandardScaler()
        self.fitted = False
        self.feature_names: List[str] = []

    def fit_transform(self, X: List[List[float]], feature_names: List[str]) -> List[List[float]]:
        import numpy as np
        self.feature_names = feature_names
        X_np = np.array(X, dtype=float)
        X_scaled = self.scaler.fit_transform(X_np)
        self.fitted = True
        return X_scaled.tolist()

    def transform(self, X: List[List[float]]) -> List[List[float]]:
        if not self.fitted:
            raise RuntimeError("Preprocessor not fitted yet. Call fit_transform first.")
        import numpy as np
        X_np = np.array(X, dtype=float)
        return self.scaler.transform(X_np).tolist()

    def transform_dict(self, feature_dict: Dict[str, float]) -> List[float]:
        """Transform a single dict (live inference from extension)."""
        row = [feature_dict.get(f, 0.0) for f in self.feature_names]
        return self.transform([row])[0]


# ── Training ───────────────────────────────────────────────────────────────────

class FatigueModelTrainer:
    """
    Trains and cross-validates all four research-recommended models.
    Selects the best by mean F1-macro across stratified k-fold.
    """

    def __init__(self, feature_names: Optional[List[str]] = None, cv_folds: int = 5):
        self.feature_names = feature_names or get_full_feature_names()
        self.cv_folds = cv_folds
        self.preprocessor = FatiguePreprocessor()
        self.best_model = None
        self.best_model_name = None
        self.cv_results: Dict = {}

    def fit(
        self,
        X: List[List[float]],
        y: List[int],
    ) -> "FatigueModelTrainer":
        """
        Train all models, select best by CV F1-macro.
        X: list of feature vectors (already ordered by self.feature_names)
        y: list of int labels (0=NORMAL, 1=ELEVATED, 2=HIGH)
        """
        from sklearn.model_selection import StratifiedKFold, cross_val_score
        import numpy as np

        X_scaled = self.preprocessor.fit_transform(X, self.feature_names)
        X_arr = np.array(X_scaled)
        y_arr = np.array(y)

        cv = StratifiedKFold(n_splits=self.cv_folds, shuffle=True, random_state=42)

        best_f1 = -1.0
        self.cv_results = {}

        for name, config in MODEL_CONFIGS.items():
            Cls = _import_class(config["module"], config["class"])
            model = Cls(**config["params"])

            scores = cross_val_score(
                model, X_arr, y_arr,
                cv=cv, scoring="f1_macro", n_jobs=-1,
            )
            mean_f1 = scores.mean()
            std_f1  = scores.std()
            self.cv_results[name] = {
                "mean_f1": round(mean_f1, 4),
                "std_f1":  round(std_f1, 4),
                "scores":  [round(s, 4) for s in scores.tolist()],
            }

            if mean_f1 > best_f1:
                best_f1 = mean_f1
                self.best_model_name = name
                self.best_model = Cls(**config["params"])

        # Train best model on full dataset
        self.best_model.fit(X_arr, y_arr)
        return self

    def get_cv_summary(self) -> str:
        lines = ["Model Selection (CV F1-macro):"]
        for name, res in sorted(self.cv_results.items(),
                                 key=lambda x: -x[1]["mean_f1"]):
            marker = " ← SELECTED" if name == self.best_model_name else ""
            lines.append(
                f"  {name:25s}  F1={res['mean_f1']:.4f} ± {res['std_f1']:.4f}{marker}"
            )
        return "\n".join(lines)


# ── Evaluation ─────────────────────────────────────────────────────────────────

class FatigueEvaluator:
    """
    Evaluates a trained model with metrics from the research (Prompt 4):
      - Accuracy
      - F1-score (macro + per-class)
      - AUC (one-vs-rest, needed for multi-class)
      - Cohen's kappa (accounts for chance agreement)
    Targets: F1-macro >= 0.70, AUC >= 0.80 (research thresholds)
    """

    @staticmethod
    def evaluate(
        model,
        preprocessor: FatiguePreprocessor,
        X_test: List[List[float]],
        y_test: List[int],
    ) -> Dict[str, Any]:
        from sklearn.metrics import (
            accuracy_score, f1_score, classification_report,
            roc_auc_score, cohen_kappa_score,
        )
        from sklearn.preprocessing import label_binarize
        import numpy as np

        X_scaled = np.array(preprocessor.transform(X_test))
        y_pred = model.predict(X_scaled)
        y_proba = None
        if hasattr(model, "predict_proba"):
            y_proba = model.predict_proba(X_scaled)

        accuracy = accuracy_score(y_test, y_pred)
        f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
        f1_per_class = f1_score(y_test, y_pred, average=None, zero_division=0).tolist()
        kappa = cohen_kappa_score(y_test, y_pred)

        # Multi-class AUC (one-vs-rest)
        auc = None
        if y_proba is not None:
            try:
                y_bin = label_binarize(y_test, classes=[0, 1, 2])
                auc = roc_auc_score(y_bin, y_proba, multi_class="ovr", average="macro")
            except Exception:
                auc = None

        report = classification_report(
            y_test, y_pred,
            target_names=LABEL_NAMES,
            zero_division=0,
        )

        # Research thresholds check
        meets_f1_target = f1_macro >= 0.70
        meets_auc_target = (auc is not None and auc >= 0.80)

        return {
            "accuracy":           round(accuracy, 4),
            "f1_macro":           round(f1_macro, 4),
            "f1_per_class":       {k: round(v, 4) for k, v in zip(LABEL_NAMES, f1_per_class)},
            "kappa":              round(kappa, 4),
            "auc_macro_ovr":      round(auc, 4) if auc is not None else None,
            "meets_f1_target":    meets_f1_target,
            "meets_auc_target":   meets_auc_target,
            "classification_report": report,
        }


# ── Inference (live, real-time) ────────────────────────────────────────────────

class FatiguePredictor:
    """
    Production inference class. Loaded from disk, takes live feature dict,
    returns structured prediction. Designed for <1ms inference.

    Usage (from FastAPI backend):
        predictor = FatiguePredictor.load("models/neurolens_model.pkl")
        result = predictor.predict(feature_dict)
    """

    def __init__(self, model, preprocessor: FatiguePreprocessor, metadata: dict):
        self.model = model
        self.preprocessor = preprocessor
        self.metadata = metadata

    def predict(self, feature_dict: Dict[str, float]) -> Dict[str, Any]:
        """
        Single-sample real-time inference.

        Args:
            feature_dict: output of features.build_feature_vector()

        Returns:
            {
              "label": "HIGH",
              "label_int": 2,
              "confidence": 0.87,
              "probabilities": {"NORMAL": 0.05, "ELEVATED": 0.08, "HIGH": 0.87},
              "performance_score": 13,   # 100 - (label_int / 2 * 100)
            }
        """
        import numpy as np

        row = [feature_dict.get(f, 0.0) for f in self.preprocessor.feature_names]
        X_scaled = np.array(self.preprocessor.transform([row]))

        label_int = int(self.model.predict(X_scaled)[0])
        label = INT_TO_LABEL[label_int]

        proba_dict = {}
        confidence = 1.0
        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(X_scaled)[0]
            proba_dict = {INT_TO_LABEL[i]: round(float(p), 4) for i, p in enumerate(proba)}
            confidence = round(float(proba[label_int]), 4)

        # Performance score: inverse of fatigue level (judge-friendly)
        performance_score = round(100 - (label_int / 2.0) * 100, 1)

        return {
            "label":             label,
            "label_int":         label_int,
            "confidence":        confidence,
            "probabilities":     proba_dict,
            "performance_score": performance_score,
            "model_version":     self.metadata.get("version", "1.0"),
        }

    def predict_batch(self, feature_dicts: List[Dict[str, float]]) -> List[Dict]:
        return [self.predict(fd) for fd in feature_dicts]

    def save(self, path: str):
        artifact = {
            "model":        self.model,
            "preprocessor": self.preprocessor,
            "metadata":     self.metadata,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Model saved to {path}")

    @classmethod
    def load(cls, path: str) -> "FatiguePredictor":
        with open(path, "rb") as f:
            artifact = pickle.load(f)
        return cls(
            model=artifact["model"],
            preprocessor=artifact["preprocessor"],
            metadata=artifact["metadata"],
        )
