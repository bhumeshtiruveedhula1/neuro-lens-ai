from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Dict, List

from schema import ThresholdProfile


@dataclass
class CalibrationSnapshot:
    thresholds: ThresholdProfile
    label_count: int
    strong_label_count: int
    notes: List[str]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def derive_thresholds(labels: List[Dict]) -> CalibrationSnapshot:
    if not labels:
        return CalibrationSnapshot(
            thresholds=ThresholdProfile(),
            label_count=0,
            strong_label_count=0,
            notes=["No self-reported labels yet, so default cutoffs are still in use."],
        )

    high_scores = [label["main_model_score"] for label in labels if label["label_kind"] in {"confirmed_high_fatigue", "severe_stress_event"}]
    safe_scores = [label["main_model_score"] for label in labels if label["label_kind"] == "confirmed_safe"]
    severe_scores = [label["main_model_score"] for label in labels if label["label_kind"] == "severe_stress_event"]

    normal_max = 40.0
    high_load_max = 65.0
    fatigued_max = 80.0
    notes: List[str] = []

    if safe_scores:
        safe_anchor = median(safe_scores)
        normal_max = _clamp(safe_anchor + 18.0, 28.0, 50.0)
        notes.append("Safe check-ins are nudging the normal range toward your own baseline.")

    if high_scores:
        high_anchor = median(high_scores)
        high_load_max = _clamp(high_anchor, normal_max + 8.0, 70.0)
        fatigued_max = _clamp(high_anchor + 14.0, high_load_max + 6.0, 85.0)
        notes.append("Reported tired moments are shifting the high-load cutoff to fit you better.")

    if severe_scores:
        severe_anchor = median(severe_scores)
        fatigued_max = _clamp(min(fatigued_max, severe_anchor + 6.0), high_load_max + 6.0, 82.0)
        notes.append("Stress-event labels are making the support trigger more sensitive.")

    reason = notes[0] if notes else "Using your self-reports to gently tune the state boundaries."
    thresholds = ThresholdProfile(
        normal_max=round(normal_max, 2),
        high_load_max=round(high_load_max, 2),
        fatigued_max=round(fatigued_max, 2),
        reason=reason,
    )
    return CalibrationSnapshot(
        thresholds=thresholds,
        label_count=len(labels),
        strong_label_count=len(high_scores) + len(safe_scores),
        notes=notes or ["Using your self-reports to gently tune the state boundaries."],
    )


def summarize_plain_state(severity: float, thresholds: ThresholdProfile) -> str:
    if severity <= thresholds.normal_max:
        return "You are in a normal range."
    if severity <= thresholds.high_load_max:
        return "Your brain is working hard."
    if severity <= thresholds.fatigued_max:
        return "You may be getting tired."
    return "You look pretty drained right now."
