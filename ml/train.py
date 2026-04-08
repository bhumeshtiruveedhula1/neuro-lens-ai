"""
NeuroLens AI -- Training Script
=================================
End-to-end pipeline:
  1. Generate (or load) dataset
  2. Engineer features
  3. Split: 80% train / 20% test (stratified)
  4. Train all 4 models, select best by CV F1-macro
  5. Evaluate on held-out test set
  6. Save model artifact to models/neurolens_model.pkl
  7. Save evaluation report to evaluation/report.json

Run:
  python train.py

To use your own real data, replace the synthetic generator with a CSV loader
and ensure column names match the feature vector defined in features.py.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# ── Try importing sklearn -- give clear error if missing ──────────────────────
try:
    from sklearn.model_selection import train_test_split
    import numpy as np
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    print("ERROR: scikit-learn not installed. Run: pip install scikit-learn numpy")
    sys.exit(1)

from ml.features import get_full_feature_names, build_feature_vector
from ml.synthetic import generate_dataset, dataset_to_arrays, LABEL_NAMES, INT_TO_LABEL
from ml.pipeline import (
    FatiguePreprocessor, FatigueModelTrainer, FatigueEvaluator,
    FatiguePredictor, LABEL_TO_INT,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
MODEL_PATH = ROOT / "models" / "neurolens_model.pkl"
REPORT_PATH = ROOT / "evaluation" / "report.json"


def load_real_data_csv(csv_path: str) -> tuple:
    """
    Placeholder for real data loading.
    CSV must have columns matching get_full_feature_names() + 'fatigue_label'.

    fatigue_label: "NORMAL" | "ELEVATED" | "HIGH"
    """
    import csv
    feature_names = get_full_feature_names()
    X, y = [], []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            features = [float(row.get(fn, 0)) for fn in feature_names]
            label = LABEL_TO_INT.get(row["fatigue_label"].strip().upper(), 0)
            X.append(features)
            y.append(label)
    return X, y, feature_names


def main(
    use_real_data: bool = False,
    real_data_path: str = "data/sessions.csv",
    n_users: int = 30,
    windows_per_user: int = 25,
    test_size: float = 0.20,
    random_state: int = 42,
):
    print("=" * 60)
    print("  NeuroLens AI -- Fatigue Detection ML Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── 1. Data ────────────────────────────────────────────────────────────────
    feature_names = get_full_feature_names()

    if use_real_data and Path(real_data_path).exists():
        print(f"\n[1/5] Loading real data from {real_data_path}...")
        X, y, feature_names = load_real_data_csv(real_data_path)
        print(f"      Loaded {len(X)} samples with {len(feature_names)} features")
    else:
        if use_real_data:
            print(f"\n[1/5] {real_data_path} not found — using synthetic data")
        else:
            print(f"\n[1/5] Generating synthetic dataset ({n_users} users × {windows_per_user} windows)...")

        X_dicts, y = generate_dataset(
            n_users=n_users,
            windows_per_user=windows_per_user,
            seed=random_state,
        )
        X, _ = dataset_to_arrays(X_dicts, y, feature_names)
        print(f"      Generated {len(X)} samples | Features: {len(feature_names)}")

    # Class distribution
    from collections import Counter
    dist = Counter(y)
    print("      Class distribution:")
    for label_int, count in sorted(dist.items()):
        pct = 100 * count / len(y)
        print(f"        {LABEL_NAMES[label_int]:10s}: {count:4d} ({pct:.1f}%)")

    # ── 2. Train/test split (stratified) ────────────────────────────────────────
    print(f"\n[2/5] Splitting: {int((1-test_size)*100)}% train / {int(test_size*100)}% test (stratified)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=random_state
    )
    print(f"      Train: {len(X_train)} samples | Test: {len(X_test)} samples")

    # ── 3. Train models (CV selection) ──────────────────────────────────────────
    print(f"\n[3/5] Training & cross-validating 4 models (5-fold CV)...")
    trainer = FatigueModelTrainer(feature_names=feature_names, cv_folds=5)
    trainer.fit(X_train, y_train)

    print("\n" + trainer.get_cv_summary())
    print(f"\n  Best model: {trainer.best_model_name}")

    # ── 4. Evaluate on held-out test set ────────────────────────────────────────
    print(f"\n[4/5] Evaluating on held-out test set...")
    eval_results = FatigueEvaluator.evaluate(
        model=trainer.best_model,
        preprocessor=trainer.preprocessor,
        X_test=X_test,
        y_test=y_test,
    )

    print("\n  Test Set Results:")
    print(f"    Accuracy:      {eval_results['accuracy']:.4f}")
    print(f"    F1-macro:      {eval_results['f1_macro']:.4f}  {'✅ >= 0.70 target' if eval_results['meets_f1_target'] else '⚠ below 0.70 target'}")
    if eval_results["auc_macro_ovr"]:
        print(f"    AUC (OvR):     {eval_results['auc_macro_ovr']:.4f}  {'✅ >= 0.80 target' if eval_results['meets_auc_target'] else '⚠ below 0.80 target'}")
    print(f"    Cohen's kappa: {eval_results['kappa']:.4f}")
    print("\n  Per-class F1:")
    for cls, f1 in eval_results["f1_per_class"].items():
        print(f"    {cls:10s}: {f1:.4f}")
    print("\n  Classification Report:")
    print(eval_results["classification_report"])

    # ── 5. Save model artifact ──────────────────────────────────────────────────
    print(f"\n[5/5] Saving model artifact...")
    metadata = {
        "version":         "1.0",
        "model_type":      trainer.best_model_name,
        "feature_names":   feature_names,
        "n_features":      len(feature_names),
        "labels":          LABEL_NAMES,
        "trained_at":      datetime.now().isoformat(),
        "n_train_samples": len(X_train),
        "cv_results":      trainer.cv_results,
        "test_results":    {k: v for k, v in eval_results.items()
                            if k != "classification_report"},
    }

    predictor = FatiguePredictor(
        model=trainer.best_model,
        preprocessor=trainer.preprocessor,
        metadata=metadata,
    )
    predictor.save(str(MODEL_PATH))

    # Save evaluation report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Evaluation report: {REPORT_PATH}")

    print("\n" + "=" * 60)
    print("  Training complete!")
    print(f"  Model: {MODEL_PATH}")
    print("=" * 60)

    return predictor


if __name__ == "__main__":
    main()
