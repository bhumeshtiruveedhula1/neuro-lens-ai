from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

import aiosqlite
from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from backend.core.database import (
    fetch_latest_feature_window,
    fetch_latest_prediction,
    fetch_prediction_count,
    fetch_prediction_history,
    fetch_recent_feature_windows,
    get_db,
)
from backend.core.metrics import ingest_metrics
from backend.core.schema import LiveState, MinuteTelemetryPayload
from backend.core.ui_mapper import build_demo_ui_payload, map_live_state_to_ui

router = APIRouter()

MEANINGFUL_INPUT_FIELDS = {
    "active_domain",
    "page_title",
    "key_count",
    "character_count",
    "backspace_count",
    "mean_key_hold",
    "std_key_hold",
    "key_hold_samples",
    "mean_interkey_latency",
    "std_interkey_latency",
    "interkey_samples",
    "typing_active_seconds",
    "active_seconds",
    "idle_seconds",
    "idle_bursts",
    "tab_switches",
    "window_switches",
    "short_video_seconds",
    "short_video_sessions",
    "eye_ear",
    "eye_blink_rate_per_min",
    "eye_closure_duration_s",
    "eye_frame_rate",
    "eye_source",
}


class PredictReasonGroups(BaseModel):
    behavior: list[str] = Field(default_factory=list)
    session: list[str] = Field(default_factory=list)
    fatigue: list[str] = Field(default_factory=list)


class PredictBaselines(BaseModel):
    typing_speed: float
    error_rate: float
    switching: float


class PredictResponse(BaseModel):
    fatigue_score: float
    state: Literal["normal", "high_load", "fatigue", "risk"]
    confidence: Literal["low", "medium", "high"]
    reasons: PredictReasonGroups
    trend: Literal["up", "down", "stable"]
    trendDelta: float
    burnoutScore: float
    distractionLevel: float
    baselines: PredictBaselines
    anomalies: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    last_updated: str
    status: Literal["calibrating", "live", "stale"]


def _has_meaningful_payload(payload: Optional[MinuteTelemetryPayload]) -> bool:
    if payload is None:
        return False
    return bool((payload.model_fields_set or set()) & MEANINGFUL_INPUT_FIELDS)


async def _load_latest_live_state(db: aiosqlite.Connection, user_id: str) -> LiveState | None:
    latest = await fetch_latest_prediction(db, user_id)
    if not latest:
        return None
    latest["current_features"] = await fetch_latest_feature_window(db, user_id)
    latest.setdefault("history_minutes", [])
    return LiveState(**latest)


@router.post("/predict", response_model=PredictResponse)
async def predict(
    payload: MinuteTelemetryPayload | None = Body(default=None),
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    now = datetime.now(UTC)

    if _has_meaningful_payload(payload):
        ingest_response = await ingest_metrics(payload, user_id=user_id, db=db)
        state = ingest_response.state
        current_features = dict(state.current_features)
    else:
        state = await _load_latest_live_state(db, user_id)
        if state is None:
            return PredictResponse(**build_demo_ui_payload(now=now))
        current_features = dict(state.current_features)

    feature_windows = await fetch_recent_feature_windows(db, user_id, limit=60)
    history = await fetch_prediction_history(db, user_id, limit=30)
    prediction_count = await fetch_prediction_count(db, user_id)

    return PredictResponse(
        **map_live_state_to_ui(
            state=state,
            current_features=current_features,
            feature_windows=feature_windows,
            history=history,
            prediction_count=prediction_count,
            now=now,
        )
    )
