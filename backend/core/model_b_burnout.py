from __future__ import annotations

from dataclasses import dataclass
from typing import List


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class BurnoutModelInput:
    avg_fatigue_score: float
    hours_in_high_load: float
    long_sessions: float
    late_night_usage_hours: float
    trend_over_days: float


@dataclass
class BurnoutModelOutput:
    burnout_risk_index: float
    insights: List[str]


class ModelBBurnout:
    """
    Burnout risk model (Model B).

    Inputs:
    - avg_fatigue_score
    - hours_in_high_load
    - long_sessions
    - late_night_usage_hours
    - trend_over_days
    """

    def predict(self, features: BurnoutModelInput) -> BurnoutModelOutput:
        fatigue_component = _clamp(features.avg_fatigue_score, 0.0, 100.0) * 0.42
        high_load_component = _clamp(features.hours_in_high_load / 6.0, 0.0, 1.0) * 25.0
        long_session_component = _clamp(features.long_sessions / 6.0, 0.0, 1.0) * 13.0
        late_night_component = _clamp(features.late_night_usage_hours / 3.0, 0.0, 1.0) * 10.0
        trend_component = _clamp((features.trend_over_days + 1.0) / 2.0, 0.0, 1.0) * 10.0

        risk = _clamp(
            fatigue_component
            + high_load_component
            + long_session_component
            + late_night_component
            + trend_component,
            0.0,
            100.0,
        )

        insights: List[str] = []
        if features.hours_in_high_load >= 2.0:
            insights.append("Multiple hours in high-load state increase burnout risk.")
        if features.long_sessions >= 2.0:
            insights.append("Frequent long sessions without breaks increase strain.")
        if features.late_night_usage_hours >= 1.0:
            insights.append("Late-night work pattern can reduce recovery quality.")
        if features.trend_over_days > 0.15:
            insights.append("Risk trend has been rising over recent days.")
        if not insights:
            insights.append("Current burnout trend is stable and relatively controlled.")

        return BurnoutModelOutput(
            burnout_risk_index=round(risk, 2),
            insights=insights,
        )
