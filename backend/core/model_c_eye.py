from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Deque, Iterable, Optional

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import mediapipe as mp  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    mp = None

logger = logging.getLogger(__name__)

# MediaPipe FaceMesh eye landmarks
LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _compute_ear(
    landmarks: Iterable[object],
    indices: tuple[int, int, int, int, int, int],
) -> float:
    points = [(float(landmarks[i].x), float(landmarks[i].y)) for i in indices]
    p1, p2, p3, p4, p5, p6 = points
    vertical = _distance(p2, p6) + _distance(p3, p5)
    horizontal = max(_distance(p1, p4), 1e-8)
    return vertical / (2.0 * horizontal)


@dataclass
class EyeFatigueResult:
    timestamp: str
    ear: float = 0.0
    blink_rate_per_min: float = 0.0
    eye_closure_duration_s: float = 0.0
    eye_fatigue_score: float = 0.0
    drowsy_flag: bool = False
    source: str = "fallback"
    warnings: list[str] = field(default_factory=list)


class ModelCEyeFatigue:
    """
    Eye fatigue / drowsiness model.
    - Uses EAR from MediaPipe FaceMesh when available.
    - Falls back to metric-only updates when camera dependencies are absent.
    """

    def __init__(
        self,
        ear_threshold: float = 0.21,
        drowsy_frame_threshold: int = 20,
        drowsy_closure_seconds: float = 1.0,
        blink_window_seconds: int = 60,
        normal_blink_rate: float = 15.0,
        default_frame_rate: float = 24.0,
    ):
        self.ear_threshold = ear_threshold
        self.drowsy_frame_threshold = drowsy_frame_threshold
        self.drowsy_closure_seconds = drowsy_closure_seconds
        self.blink_window_seconds = blink_window_seconds
        self.normal_blink_rate = normal_blink_rate
        self.default_frame_rate = default_frame_rate

        self._closed_run_frames = 0
        self._was_closed = False
        self._blink_timestamps: Deque[float] = deque(maxlen=300)
        self._last_result: Optional[EyeFatigueResult] = None

        self._face_mesh = None
        if mp is not None:  # pragma: no branch - simple availability gate
            try:
                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                logger.warning("Eye model: failed to initialize FaceMesh (%s)", exc)

    @property
    def last_result(self) -> Optional[EyeFatigueResult]:
        return self._last_result

    def _to_datetime(self, timestamp: Optional[datetime | str]) -> datetime:
        if isinstance(timestamp, datetime):
            return timestamp
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp)
            except Exception:
                return _utc_now()
        return _utc_now()

    def _compute_blink_rate(self, now_ts: float) -> float:
        while self._blink_timestamps and now_ts - self._blink_timestamps[0] > self.blink_window_seconds:
            self._blink_timestamps.popleft()
        return (len(self._blink_timestamps) * 60.0) / max(float(self.blink_window_seconds), 1.0)

    def _score(self, ear: float, blink_rate: float, closure_seconds: float, drowsy_flag: bool) -> float:
        ear_component = max(0.0, self.ear_threshold - ear) * 220.0
        closure_component = min(45.0, closure_seconds * 22.0)
        blink_deviation = abs(blink_rate - self.normal_blink_rate) / max(self.normal_blink_rate, 1.0)
        blink_component = min(35.0, blink_deviation * 45.0)
        drowsy_boost = 20.0 if drowsy_flag else 0.0
        return round(_clamp(ear_component + closure_component + blink_component + drowsy_boost, 0.0, 100.0), 2)

    def update_from_metrics(
        self,
        *,
        ear: Optional[float] = None,
        blink_rate_per_min: Optional[float] = None,
        closure_duration_s: Optional[float] = None,
        frame_rate: Optional[float] = None,
        timestamp: Optional[datetime | str] = None,
        source: str = "manual",
    ) -> EyeFatigueResult:
        moment = self._to_datetime(timestamp)
        fps = max(float(frame_rate or self.default_frame_rate), 1.0)
        warnings: list[str] = []

        if ear is not None:
            ear = float(ear)
            if ear < self.ear_threshold:
                self._closed_run_frames += 1
                self._was_closed = True
            else:
                if self._was_closed and self._closed_run_frames >= 2:
                    self._blink_timestamps.append(moment.timestamp())
                self._closed_run_frames = 0
                self._was_closed = False
        elif self._last_result:
            ear = self._last_result.ear
        else:
            ear = self.ear_threshold
            warnings.append("missing_ear_signal")

        closure_seconds = (
            float(closure_duration_s)
            if closure_duration_s is not None
            else float(self._closed_run_frames) / fps
        )

        computed_blink_rate = self._compute_blink_rate(moment.timestamp())
        blink_rate = float(blink_rate_per_min) if blink_rate_per_min is not None else computed_blink_rate

        drowsy_flag = (
            self._closed_run_frames >= self.drowsy_frame_threshold
            or closure_seconds >= self.drowsy_closure_seconds
        )
        score = self._score(ear=ear, blink_rate=blink_rate, closure_seconds=closure_seconds, drowsy_flag=drowsy_flag)

        result = EyeFatigueResult(
            timestamp=moment.isoformat(),
            ear=round(ear, 5),
            blink_rate_per_min=round(blink_rate, 3),
            eye_closure_duration_s=round(closure_seconds, 4),
            eye_fatigue_score=score,
            drowsy_flag=bool(drowsy_flag),
            source=source,
            warnings=warnings,
        )
        self._last_result = result
        return result

    def process_frame(
        self,
        frame_bgr: object,
        *,
        timestamp: Optional[datetime | str] = None,
        frame_rate: Optional[float] = None,
    ) -> EyeFatigueResult:
        if cv2 is None or self._face_mesh is None:
            result = self.update_from_metrics(
                timestamp=timestamp,
                frame_rate=frame_rate,
                source="fallback",
            )
            if "opencv_or_mediapipe_unavailable" not in result.warnings:
                result.warnings.append("opencv_or_mediapipe_unavailable")
            self._last_result = result
            return result

        try:  # pragma: no cover - depends on runtime camera frames
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            parsed = self._face_mesh.process(rgb)
        except Exception as exc:
            logger.warning("Eye model: frame processing failed (%s)", exc)
            result = self.update_from_metrics(timestamp=timestamp, frame_rate=frame_rate, source="fallback")
            result.warnings.append("frame_processing_error")
            self._last_result = result
            return result

        if not getattr(parsed, "multi_face_landmarks", None):
            result = self.update_from_metrics(timestamp=timestamp, frame_rate=frame_rate, source="camera")
            result.warnings.append("face_not_detected")
            self._last_result = result
            return result

        landmarks = parsed.multi_face_landmarks[0].landmark
        left_ear = _compute_ear(landmarks, LEFT_EYE_IDX)
        right_ear = _compute_ear(landmarks, RIGHT_EYE_IDX)
        ear = (left_ear + right_ear) / 2.0
        return self.update_from_metrics(
            ear=ear,
            frame_rate=frame_rate,
            timestamp=timestamp,
            source="camera",
        )
