"""
NeuroLens AI -- Synthetic Dataset Generator
=============================================
Generates realistic training data based on the behavioral signatures
described in the research literature (Prompts 1-4).

Why synthetic data first:
  1. You need SOMETHING to train on before you collect real labels
  2. The distributions are grounded in actual research numbers
  3. In a hackathon you can demo a real trained model, not just a formula

Real labels should come from:
  - NASA-TLX self-reports (validated scale, mentioned in research)
  - Single-item fatigue VAS 0-10
  - Condition labels (focused session vs multitasking vs deadline pressure)

Research-grounded parameter sources:
  - Typing speed: typical range 120-350 cpm; drops ~20-35% under fatigue
  - Error rate: ~3-5% normal, up to 20-25% under high load (SWELL-KW)
  - Inter-key latency: 150-250ms normal; rises to 300-600ms under fatigue
  - Tab switches: <3/30s normal; 8-15/30s under distraction/overload
  - De Jong et al.: IKI rises monotonically with time-on-task in fatigued state
"""

from __future__ import annotations
import random
import math
from typing import List, Dict, Tuple

# ── Research-derived distribution parameters ───────────────────────────────────
# (means and stds calibrated from SWELL-KW, de Jong et al., keystroke fatigue papers)

PROFILES = {
    # NORMAL: fresh, focused cognitive work
    "NORMAL": {
        "wpm_mean": 52,        "wpm_std": 8,
        "error_rate_mean": 0.04,  "error_rate_std": 0.02,
        "latency_mean": 190,      "latency_std": 30,
        "burstiness_mean": 80,    "burstiness_std": 25,
        "hold_mean": 68,          "hold_std": 12,
        "tab_switches_mean": 2,   "tab_switches_std": 1.5,
        "idle_mean": 0.5,         "idle_std": 0.5,
        "active_ratio_mean": 0.82,"active_ratio_std": 0.08,
        "session_hours_mean": 0.5,"session_hours_std": 0.3,
    },
    # ELEVATED: moderate fatigue, ~1-2h into session under some pressure
    "ELEVATED": {
        "wpm_mean": 42,        "wpm_std": 9,
        "error_rate_mean": 0.10,  "error_rate_std": 0.04,
        "latency_mean": 290,      "latency_std": 55,
        "burstiness_mean": 150,   "burstiness_std": 50,
        "hold_mean": 82,          "hold_std": 18,
        "tab_switches_mean": 6,   "tab_switches_std": 2.5,
        "idle_mean": 3,           "idle_std": 2,
        "active_ratio_mean": 0.62,"active_ratio_std": 0.12,
        "session_hours_mean": 2.0,"session_hours_std": 0.5,
    },
    # HIGH: significant fatigue, deadline pressure, or >3h continuous work
    # Parameters align with SWELL-KW stress condition and keystroke fatigue papers
    "HIGH": {
        "wpm_mean": 32,        "wpm_std": 10,
        "error_rate_mean": 0.19,  "error_rate_std": 0.06,
        "latency_mean": 420,      "latency_std": 90,
        "burstiness_mean": 240,   "burstiness_std": 80,
        "hold_mean": 98,          "hold_std": 25,
        "tab_switches_mean": 10,  "tab_switches_std": 3,
        "idle_mean": 8,           "idle_std": 4,
        "active_ratio_mean": 0.45,"active_ratio_std": 0.15,
        "session_hours_mean": 3.5,"session_hours_std": 0.8,
    },
}

LABEL_NAMES = ["NORMAL", "ELEVATED", "HIGH"]
LABEL_TO_INT = {k: i for i, k in enumerate(LABEL_NAMES)}
INT_TO_LABEL = {v: k for k, v in LABEL_TO_INT.items()}


def _gauss_clamp(mean: float, std: float, lo: float, hi: float) -> float:
    v = random.gauss(mean, std)
    return max(lo, min(hi, v))


def _simulate_window(profile: str, user_baseline: Dict) -> Dict[str, float]:
    """
    Simulate one 30s window for the given profile.
    user_baseline introduces between-subject variability (each user has a
    slightly different 'normal' -- matching the research observation that
    per-user models outperform population models).
    """
    p = PROFILES[profile]
    b = user_baseline

    # Apply user-specific offset to simulate personal baseline variation
    wpm = _gauss_clamp(
        (p["wpm_mean"] + b.get("wpm_offset", 0)),
        p["wpm_std"], 10, 150
    )
    error_rate = _gauss_clamp(
        (p["error_rate_mean"] * b.get("error_scale", 1.0)),
        p["error_rate_std"], 0.0, 0.5
    )
    latency = _gauss_clamp(
        (p["latency_mean"] + b.get("latency_offset", 0)),
        p["latency_std"], 50, 1500
    )
    burstiness = _gauss_clamp(p["burstiness_mean"], p["burstiness_std"], 10, 600)
    hold_duration = _gauss_clamp(p["hold_mean"], p["hold_std"], 30, 300)
    tab_switches = max(0, round(_gauss_clamp(
        p["tab_switches_mean"], p["tab_switches_std"], 0, 20
    )))
    idle_s = max(0, _gauss_clamp(p["idle_mean"], p["idle_std"], 0, 25))
    active_ratio = _gauss_clamp(
        p["active_ratio_mean"], p["active_ratio_std"], 0.1, 1.0
    )
    session_hours = max(0.05, _gauss_clamp(
        p["session_hours_mean"], p["session_hours_std"], 0.05, 8.0
    ))

    # Derived
    typing_speed_cpm = wpm * 5
    cognitive_load_index = (
        0.3 * error_rate +
        0.3 * min(1.0, latency / 600) +
        0.2 * min(1.0, tab_switches / 12) +
        0.2 * (1 - active_ratio)
    )
    session_fatigue_amp = min(0.3, max(0.0, (session_hours - 2.0) * 0.05))

    # Approximate SWELL-KW error features from error_rate
    error_key_ratio = error_rate * 1.1   # close to ErrorKeyRatio
    characters_ratio = max(0, 1 - error_rate * 0.8)
    backspace_pct = error_rate * 100

    # Pause ratio: more pauses under fatigue (daytime fatigue paper)
    pause_ratio = min(0.9, error_rate * 2 + idle_s / 30)

    return {
        "wpm":                  round(wpm, 2),
        "typing_speed_cpm":     round(typing_speed_cpm, 2),
        "error_rate":           round(error_rate, 4),
        "avg_latency_ms":       round(latency, 2),
        "burstiness_ms":        round(burstiness, 2),
        "avg_hold_duration_ms": round(hold_duration, 2),
        "tab_switches":         tab_switches,
        "idle_time_s":          round(idle_s, 2),
        "session_duration_s":   round(session_hours * 3600, 1),
        "active_time_ratio":    round(active_ratio, 3),
        "mean_PP":              round(latency, 2),
        "std_PP":               round(burstiness, 2),
        "p90_PP":               round(latency + 1.5 * burstiness, 2),
        "mean_HT":              round(hold_duration, 2),
        "std_HT":               round(hold_duration * 0.2, 2),
        "error_key_ratio":      round(error_key_ratio, 4),
        "characters_ratio":     round(characters_ratio, 4),
        "backspace_pct":        round(backspace_pct, 3),
        "pause_ratio":          round(pause_ratio, 4),
        "delta_wpm":            round(random.gauss(-3 if profile != "NORMAL" else 0, 3), 2),
        "delta_error_rate":     round(random.gauss(0.02 if profile != "NORMAL" else 0, 0.01), 4),
        "wpm_slope":            round(random.gauss(-0.5 if profile != "NORMAL" else 0, 0.5), 4),
        "cognitive_load_index": round(cognitive_load_index, 4),
        "session_fatigue_amp":  round(session_fatigue_amp, 4),
    }


def generate_dataset(
    n_users: int = 30,
    windows_per_user: int = 20,
    class_weights: Tuple[float, float, float] = (0.40, 0.35, 0.25),
    seed: int = 42,
) -> Tuple[List[Dict[str, float]], List[int]]:
    """
    Generate a realistic synthetic dataset.

    n_users: number of simulated users (each with their own baseline)
    windows_per_user: number of 30s windows per user
    class_weights: (NORMAL, ELEVATED, HIGH) proportions -- based on
                   research finding 57-75% of users show some fatigue

    Returns: (X, y) where X is list of feature dicts, y is list of int labels
    """
    random.seed(seed)

    # Assign labels proportionally (stratified across users)
    label_counts = [
        round(class_weights[0] * windows_per_user),
        round(class_weights[1] * windows_per_user),
        round(class_weights[2] * windows_per_user),
    ]
    # Fix rounding to exactly windows_per_user
    while sum(label_counts) < windows_per_user:
        label_counts[0] += 1
    while sum(label_counts) > windows_per_user:
        label_counts[-1] -= 1

    X: List[Dict[str, float]] = []
    y: List[int] = []

    for user_idx in range(n_users):
        # Each user has a personal baseline offset
        # This simulates between-subject variability (CMU keystroke stress finding:
        # population models struggle; per-user baselines help)
        user_baseline = {
            "wpm_offset":     random.gauss(0, 10),    # ±10 wpm personal variation
            "latency_offset": random.gauss(0, 30),    # ±30ms personal variation
            "error_scale":    max(0.3, random.gauss(1.0, 0.3)),  # personal error tendency
        }

        # Build window sequence for this user: simulate temporal progression
        user_labels = (
            [LABEL_TO_INT["NORMAL"]]   * label_counts[0] +
            [LABEL_TO_INT["ELEVATED"]] * label_counts[1] +
            [LABEL_TO_INT["HIGH"]]     * label_counts[2]
        )
        random.shuffle(user_labels)

        for label_int in user_labels:
            label_name = INT_TO_LABEL[label_int]
            feats = _simulate_window(label_name, user_baseline)
            X.append(feats)
            y.append(label_int)

    return X, y


def dataset_to_arrays(X: List[Dict], y: List[int], feature_names: List[str]):
    """Convert list of dicts + labels to numpy-style lists for sklearn."""
    X_arr = [[row.get(f, 0.0) for f in feature_names] for row in X]
    return X_arr, y
