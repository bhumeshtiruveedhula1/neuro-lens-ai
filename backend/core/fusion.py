from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class FusionResult:
    final_fatigue_score: float
    alert_level: str
    eye_fatigue_score: float
    drowsy_flag: bool
    alerts: List[Dict[str, Any]] = field(default_factory=list)


def fuse_scores(
    *,
    fatigue_score: float,
    load_score: float,
    eye_fatigue_score: float,
    drowsy_flag: bool,
) -> FusionResult:
    behavioral = max(float(fatigue_score), float(load_score))
    eye = float(eye_fatigue_score)

    behavior_high = behavioral >= 70.0
    eye_high = eye >= 65.0 or bool(drowsy_flag)

    if behavior_high and eye_high:
        alert_level = "strong"
        final_score = _clamp(0.55 * behavioral + 0.45 * eye + 10.0, 0.0, 100.0)
    elif behavior_high or eye_high:
        alert_level = "moderate"
        final_score = _clamp(0.65 * behavioral + 0.35 * eye + 5.0, 0.0, 100.0)
    else:
        alert_level = "low"
        final_score = _clamp(0.72 * behavioral + 0.28 * eye, 0.0, 100.0)

    return FusionResult(
        final_fatigue_score=round(final_score, 2),
        alert_level=alert_level,
        eye_fatigue_score=round(eye, 2),
        drowsy_flag=bool(drowsy_flag),
    )


def build_realtime_alerts(
    *,
    fatigue_score: float,
    load_score: float,
    eye_fatigue_score: float,
    drowsy_flag: bool,
    eye_closure_duration_s: float,
    blink_rate_per_min: float,
    model_a_reasons: List[str],
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    top_behavior_reasons = model_a_reasons[:3] if model_a_reasons else ["Behavioral features moved away from baseline."]

    if load_score >= 70:
        alerts.append(
            {
                "title": "High cognitive load",
                "severity": "high",
                "message": "Behavioral Model A indicates sustained cognitive load.",
                "reasons": top_behavior_reasons[:2],
            }
        )

    if fatigue_score >= 65 or eye_fatigue_score >= 65:
        fatigue_reasons = list(top_behavior_reasons[:2])
        fatigue_reasons.append(
            f"Eye fatigue score {round(eye_fatigue_score, 1)} with blink rate {round(blink_rate_per_min, 1)}/min."
        )
        alerts.append(
            {
                "title": "Fatigue detected",
                "severity": "high" if fatigue_score >= 75 or eye_fatigue_score >= 75 else "medium",
                "message": "Behavioral and eye signals suggest fatigue.",
                "reasons": fatigue_reasons,
            }
        )

    if drowsy_flag or eye_closure_duration_s >= 1.0:
        alerts.append(
            {
                "title": "Possible drowsiness",
                "severity": "critical" if eye_closure_duration_s >= 1.5 else "high",
                "message": "Eyes stayed closed longer than normal.",
                "reasons": [
                    f"Continuous eye closure: {round(eye_closure_duration_s, 2)}s.",
                    f"Blink rate: {round(blink_rate_per_min, 1)}/min.",
                ],
            }
        )

    return alerts
