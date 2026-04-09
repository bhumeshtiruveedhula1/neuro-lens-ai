from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, Tuple


def _std(values: Iterable[float]) -> float:
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((value - mean) ** 2 for value in vals) / (len(vals) - 1)
    return math.sqrt(max(variance, 0.0))


@dataclass
class RollingBaseline:
    """
    Rolling mean/std per feature per user for personalization.

    Stats are computed from prior windows only; the current window is added
    after z-scores are generated.
    """

    max_windows: int = 16 * 60
    _history: Dict[str, Deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque()))

    def snapshot(self, feature_vector: Dict[str, float]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for name, current in feature_vector.items():
            if not isinstance(current, (int, float)):
                continue
            values = self._history[name]
            if values:
                mean = sum(values) / len(values)
                std = _std(values)
            else:
                mean = float(current)
                std = 0.0
            result[f"rolling_mean_{name}"] = round(float(mean), 6)
            result[f"rolling_std_{name}"] = round(float(std), 6)
            if std > 1e-6:
                z = (float(current) - mean) / std
            else:
                z = 0.0
            result[f"z_{name}"] = round(float(z), 6)
        return result

    def update(self, feature_vector: Dict[str, float]) -> None:
        for name, value in feature_vector.items():
            if not isinstance(value, (int, float)):
                continue
            history = self._history[name]
            history.append(float(value))
            while len(history) > self.max_windows:
                history.popleft()

    def count(self, feature_name: str) -> int:
        return len(self._history.get(feature_name, ()))

    def mean_std(self, feature_name: str) -> Tuple[float, float]:
        history = self._history.get(feature_name, ())
        if not history:
            return 0.0, 0.0
        mean = sum(history) / len(history)
        std = _std(history)
        return float(mean), float(std)
