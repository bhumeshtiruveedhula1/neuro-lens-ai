from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

import aiosqlite
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from backend.core.pipeline import PIPELINE
from backend.core.calibration import derive_thresholds
from backend.core.cognitive_engine import ENGINE
from backend.core.companion import build_first_week_prompt, build_proactive_message, build_welcome_sequence, respond_to_user_message
from backend.core.database import (
    fetch_calibration_labels,
    fetch_chat_events,
    fetch_burnout_inputs,
    fetch_daily_burnout_snapshot,
    fetch_distinct_prediction_days,
    fetch_latest_feature_window,
    fetch_latest_eye_observation,
    fetch_latest_prediction,
    fetch_notifications,
    fetch_prediction_count,
    fetch_prediction_history,
    fetch_profile,
    fetch_prompt_count_for_day,
    fetch_recent_feature_windows,
    fetch_self_reports,
    fetch_today_summary,
    fetch_unread_chat_count,
    fetch_recent_telemetry,
    fetch_video_sessions,
    fetch_video_summary,
    get_db,
    insert_calibration_label,
    insert_chat_event,
    insert_feature_window,
    insert_eye_observation,
    insert_minute_telemetry,
    insert_notification,
    insert_prediction,
    insert_self_report,
    insert_video_session,
    mark_chat_read,
    reset_user_data,
    upsert_personalization_stats,
    upsert_profile,
)
from backend.core.model_b_burnout import BurnoutModelInput, ModelBBurnout
from backend.core.schema import (
    BurnoutTrendResponse,
    CalibrationStatusResponse,
    ChatMessage,
    ChatSendResponse,
    ChatThreadResponse,
    ChatUserMessagePayload,
    EyeFatigueStateResponse,
    EyeMetricsPayload,
    AppBreakdownResponse,
    ExplanationItem,
    HistoryPoint,
    HistoryResponse,
    IngestResponse,
    LiveState,
    MinuteTelemetryPayload,
    NotificationFeedResponse,
    NotificationMessage,
    OnboardingProfile,
    ProfileResponse,
    RealtimeAlert,
    StateLabel,
    SelfReportPayload,
    SelfReportRecord,
    SelfReportResponse,
    TelemetryPoint,
    TelemetryRecentResponse,
    TodaySummary,
    VideoSessionListResponse,
    VideoSessionPayload,
    VideoSessionRecord,
    VideoSummaryResponse,
)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if websocket in self.connections.get(user_id, []):
            self.connections[user_id].remove(websocket)

    async def broadcast(self, user_id: str, payload: dict):
        dead = []
        for websocket in self.connections.get(user_id, []):
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(user_id, websocket)


manager = ConnectionManager()
BURNOUT_MODEL = ModelBBurnout()


async def _build_burnout_risk_index(db: aiosqlite.Connection, user_id: str, fatigue_score: float, load_score: float) -> tuple[float, list[str]]:
    snapshot = await fetch_daily_burnout_snapshot(db, user_id)
    try:
        model_inputs = await fetch_burnout_inputs(db, user_id, days=14)
        current_mix = float(fatigue_score) * 0.65 + float(load_score) * 0.35
        model_inputs["avg_fatigue_score"] = max(float(model_inputs.get("avg_fatigue_score", 0.0)), current_mix)

        result = BURNOUT_MODEL.predict(
            BurnoutModelInput(
                avg_fatigue_score=float(model_inputs.get("avg_fatigue_score", 0.0)),
                hours_in_high_load=float(model_inputs.get("hours_in_high_load", 0.0)),
                long_sessions=float(model_inputs.get("long_sessions", 0.0)),
                late_night_usage_hours=float(model_inputs.get("late_night_usage_hours", 0.0)),
                trend_over_days=float(model_inputs.get("trend_over_days", 0.0)),
            )
        )

        risk = max(float(snapshot.get("burnout_risk_index", 0.0)), result.burnout_risk_index)
        insights = list(result.insights)
    except Exception:
        risk = max(float(snapshot.get("burnout_risk_index", 0.0)), float(fatigue_score) * 0.65 + float(load_score) * 0.35)
        insights = ["Burnout model fallback active; using robust heuristic risk."]

    if float(snapshot.get("total_high_load_minutes_today", 0.0)) >= 90:
        insights.append("You spent a lot of today in a heavy mental zone.")
    if int(snapshot.get("consecutive_high_days", 0)) >= 2:
        insights.append("This pattern has been showing up for more than one day.")
    return round(min(risk, 100.0), 2), insights

async def _ensure_welcome_messages(db: aiosqlite.Connection, user_id: str) -> None:
    existing = await fetch_chat_events(db, user_id, limit=2)
    if existing:
        return
    for message in build_welcome_sequence():
        await insert_chat_event(db, user_id, message)


async def _store_calibration_from_report(
    db: aiosqlite.Connection,
    user_id: str,
    report_id: int,
    report: SelfReportPayload,
    prediction: Optional[dict],
) -> None:
    if not prediction:
        return
    score = max(prediction.get("fatigue_score", 0.0), prediction.get("load_score", 0.0))
    if report.severe_stress_event:
        await insert_calibration_label(db, user_id, "severe_stress_event", 1.0, score, None, report_id)
    if report.fatigue_level is not None:
        if report.fatigue_level >= 8:
            await insert_calibration_label(db, user_id, "confirmed_high_fatigue", report.fatigue_level, score, None, report_id)
        elif report.fatigue_level <= 2:
            await insert_calibration_label(db, user_id, "confirmed_safe", report.fatigue_level, score, None, report_id)
    if report.fogginess is not None:
        if report.fogginess >= 8:
            await insert_calibration_label(db, user_id, "confirmed_high_fatigue", report.fogginess, score, None, report_id)
        elif report.fogginess <= 2:
            await insert_calibration_label(db, user_id, "confirmed_safe", report.fogginess, score, None, report_id)


async def _make_today_summary(db: aiosqlite.Connection, user_id: str) -> TodaySummary:
    raw = await fetch_today_summary(db, user_id)
    return TodaySummary(
        deep_focus_minutes=raw["deep_focus_minutes"],
        high_fatigue_minutes=raw["high_fatigue_minutes"],
        breaks_taken=int(raw["breaks_taken"]),
    )


async def _maybe_emit_companion_messages(
    db: aiosqlite.Connection,
    user_id: str,
    state: LiveState,
    profile: OnboardingProfile,
    recent_app: Optional[str],
) -> list[ChatMessage]:
    prompts_today = await fetch_prompt_count_for_day(db, user_id)
    messages: list[ChatMessage] = []

    proactive = build_proactive_message(state, prompts_today)
    if proactive:
        messages.append(proactive)
        prompts_today += 1

    first_week_prompt = build_first_week_prompt(profile, recent_app, prompts_today)
    if first_week_prompt:
        messages.append(first_week_prompt)

    for message in messages:
        await insert_chat_event(db, user_id, message)
        await manager.broadcast(user_id, {"type": "CHAT_MESSAGE", "message": message.model_dump()})
    return messages


@router.post("/profile/onboarding", response_model=ProfileResponse)
async def save_onboarding_profile(
    profile: OnboardingProfile,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    profile.onboarding_complete = True
    saved = await upsert_profile(db, user_id, profile)
    await _ensure_welcome_messages(db, user_id)
    return ProfileResponse(**saved)


@router.get("/profile/onboarding", response_model=ProfileResponse)
async def get_onboarding_profile(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    saved = await fetch_profile(db, user_id)
    await _ensure_welcome_messages(db, user_id)
    return ProfileResponse(**saved)


@router.post("/self-reports", response_model=SelfReportResponse)
async def save_self_report(
    report: SelfReportPayload,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    latest_prediction = await fetch_latest_prediction(db, user_id)
    report_id = await insert_self_report(db, user_id, report)
    await _store_calibration_from_report(db, user_id, report_id, report, latest_prediction)
    record = SelfReportRecord(
        id=report_id,
        user_id=user_id,
        timestamp=datetime.now(UTC).isoformat(),
        report_type=report.report_type,
        fatigue_level=report.fatigue_level,
        stress_level=report.stress_level,
        fogginess=report.fogginess,
        work_balance=report.work_balance,
        break_preference=report.break_preference,
        severe_stress_event=report.severe_stress_event,
        note=report.note,
        related_window_end=report.related_window_end,
        answer_values=report.answer_values,
    )
    return SelfReportResponse(report=record)


@router.get("/chat/thread", response_model=ChatThreadResponse)
async def get_chat_thread(
    user_id: str = Query("default"),
    mark_read: bool = Query(False),
    db: aiosqlite.Connection = Depends(get_db),
):
    await _ensure_welcome_messages(db, user_id)
    if mark_read:
        await mark_chat_read(db, user_id)
    messages = await fetch_chat_events(db, user_id)
    unread_count = await fetch_unread_chat_count(db, user_id)
    return ChatThreadResponse(user_id=user_id, messages=messages, unread_count=unread_count)


@router.post("/chat/message", response_model=ChatSendResponse)
async def send_chat_message(
    payload: ChatUserMessagePayload,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    user_message = None
    if payload.text or payload.quick_reply_action:
        user_message = ChatMessage(
            id=f"user-{uuid4()}",
            role="user",
            kind="reply",
            text=payload.text or payload.quick_reply_action.replace("_", " "),
            created_at=datetime.now(UTC).isoformat(),
            quick_replies=[],
            metadata={"action": payload.quick_reply_action, "payload": payload.quick_reply_payload},
            unread=False,
        )
        await insert_chat_event(db, user_id, user_message)

    assistant_messages, suggested_report, _ = respond_to_user_message(payload)
    for message in assistant_messages:
        await insert_chat_event(db, user_id, message)

    if payload.quick_reply_action == "set_break_style":
        current = await fetch_profile(db, user_id)
        profile = current["profile"]
        profile.break_style = payload.quick_reply_payload.get("break_style", profile.break_style)
        profile.onboarding_complete = True
        await upsert_profile(db, user_id, profile)
    elif payload.quick_reply_action == "classify_app":
        current = await fetch_profile(db, user_id)
        profile = current["profile"]
        app = payload.quick_reply_payload.get("app", "").lower()
        bucket = payload.quick_reply_payload.get("bucket")
        if app:
            if bucket == "focus" and app not in profile.focus_apps:
                profile.focus_apps.append(app)
            if bucket == "distraction" and app not in profile.distraction_apps:
                profile.distraction_apps.append(app)
            profile.onboarding_complete = True
            await upsert_profile(db, user_id, profile)

    if suggested_report:
        latest_prediction = await fetch_latest_prediction(db, user_id)
        report_id = await insert_self_report(db, user_id, suggested_report)
        await _store_calibration_from_report(db, user_id, report_id, suggested_report, latest_prediction)

    return ChatSendResponse(user_message=user_message, assistant_messages=assistant_messages, suggested_self_report=suggested_report)


@router.get("/calibration/status", response_model=CalibrationStatusResponse)
async def get_calibration_status(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    labels = await fetch_calibration_labels(db, user_id)
    snapshot = derive_thresholds(labels)
    return CalibrationStatusResponse(
        user_id=user_id,
        thresholds=snapshot.thresholds,
        label_count=snapshot.label_count,
        strong_label_count=snapshot.strong_label_count,
        notes=snapshot.notes,
    )


@router.post("/metrics", response_model=IngestResponse)
async def ingest_metrics(
    payload: MinuteTelemetryPayload,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    await _ensure_welcome_messages(db, user_id)
    profile_record = await fetch_profile(db, user_id)
    profile = profile_record["profile"]

    normalized_payload, missing_inputs = PIPELINE.normalize_telemetry_payload(payload)

    await insert_minute_telemetry(db, user_id, normalized_payload)
    ENGINE.append_window(user_id, normalized_payload)

    if (
        normalized_payload.eye_ear is not None
        or normalized_payload.eye_blink_rate_per_min is not None
        or normalized_payload.eye_closure_duration_s is not None
    ):
        eye_result = PIPELINE.ingest_eye_metrics(
            user_id,
            ear=normalized_payload.eye_ear,
            blink_rate_per_min=normalized_payload.eye_blink_rate_per_min,
            closure_duration_s=normalized_payload.eye_closure_duration_s,
            frame_rate=normalized_payload.eye_frame_rate,
            timestamp=normalized_payload.timestamp,
            source=normalized_payload.eye_source or "extension",
        )
        await insert_eye_observation(
            db,
            user_id,
            {
                "timestamp": eye_result.timestamp,
                "source": eye_result.source,
                "ear": eye_result.ear,
                "blink_rate_per_min": eye_result.blink_rate_per_min,
                "eye_closure_duration_s": eye_result.eye_closure_duration_s,
                "eye_fatigue_score": eye_result.eye_fatigue_score,
                "drowsy_flag": eye_result.drowsy_flag,
                "warnings": eye_result.warnings,
            },
        )

    recent_windows = ENGINE.get_recent_windows(user_id, limit=5)
    rolling_reference = await fetch_recent_feature_windows(db, user_id, limit=120)
    features = ENGINE.build_feature_vector(user_id, profile, recent_windows, rolling_reference)
    await upsert_personalization_stats(db, user_id, PIPELINE.extract_personalization_stats(features))

    prediction_count = await fetch_prediction_count(db, user_id)
    distinct_days = await fetch_distinct_prediction_days(db, user_id)
    maturity = ENGINE.model_maturity(profile, prediction_count, distinct_days)

    calibration_snapshot = derive_thresholds(await fetch_calibration_labels(db, user_id))
    rough_risk, burnout_insights = await _build_burnout_risk_index(db, user_id, 0, 0)
    today_summary = await _make_today_summary(db, user_id)

    try:
        state, notification, _ = ENGINE.derive_state(
            user_id=user_id,
            timestamp=normalized_payload.timestamp,
            profile=profile,
            features=features,
            maturity=maturity,
            burnout_risk_index=rough_risk,
            thresholds=calibration_snapshot.thresholds,
            today_summary=today_summary,
        )
    except Exception:
        fallback_fatigue = max(0.0, min(100.0, float(features.get("idle_ratio", 0.0)) * 90.0 + float(features.get("current_session_length_min", 0.0)) * 0.25))
        fallback_load = max(0.0, min(100.0, float(features.get("tab_switches_per_min", 0.0)) * 18.0 + float(features.get("fragmentation_index", 0.0)) * 22.0))
        fallback_label = (
            StateLabel.FATIGUED
            if max(fallback_fatigue, fallback_load) >= 65
            else StateLabel.HIGH_LOAD
            if max(fallback_fatigue, fallback_load) >= 40
            else StateLabel.NORMAL
        )
        state = LiveState(
            user_id=user_id,
            timestamp=normalized_payload.timestamp.isoformat(),
            state_label=fallback_label,
            fatigue_score=round(fallback_fatigue, 2),
            load_score=round(fallback_load, 2),
            confidence=0.35,
            confidence_level="LOW",
            confidence_components={
                "data_sufficiency": round(float(maturity), 4),
                "probability_sharpness": 0.0,
                "temporal_consistency": 0.25,
                "composite": 0.2,
            },
            model_maturity=maturity,
            burnout_risk_index=rough_risk,
            p_fatigue=round(fallback_fatigue / 100.0, 3),
            p_high_load=round(fallback_load / 100.0, 3),
            instant_fatigue_score=round(fallback_fatigue, 2),
            instant_load_score=round(fallback_load, 2),
            smoothed_fatigue_score=round(fallback_fatigue, 2),
            smoothed_load_score=round(fallback_load, 2),
            explanation=[
                ExplanationItem(
                    feature="fallback_pipeline",
                    direction="up",
                    impact=0.5,
                    reason="Model A inference failed; running safe heuristic fallback.",
                )
            ],
            insights=["Behavioral fallback mode active while full model recovers."],
            current_features={key: round(float(value), 6) for key, value in features.items()},
            history_minutes=ENGINE.build_history_strip(user_id),
            notification=None,
            thresholds=calibration_snapshot.thresholds,
            plain_summary="Fallback mode active. Monitoring available behavioral signals.",
            today_summary=today_summary,
        )
        notification = None
    final_risk, burnout_insights = await _build_burnout_risk_index(db, user_id, state.fatigue_score, state.load_score)
    state.burnout_risk_index = final_risk
    state.thresholds = calibration_snapshot.thresholds
    state.insights.extend([item for item in burnout_insights if item not in state.insights])
    state.insights.extend([item for item in calibration_snapshot.notes if item not in state.insights])
    state.history_minutes = ENGINE.build_history_strip(user_id)
    state.today_summary = await _make_today_summary(db, user_id)

    fused = PIPELINE.fuse_state(
        user_id=user_id,
        fatigue_score=state.fatigue_score,
        load_score=state.load_score,
        model_a_reasons=[item.reason for item in state.explanation],
    )
    eye_state = PIPELINE.latest_eye_state(user_id)
    state.eye_fatigue_score = fused.eye_fatigue_score
    state.drowsy_flag = fused.drowsy_flag
    state.final_fatigue_score = fused.final_fatigue_score
    state.alert_level = fused.alert_level
    state.alerts = [RealtimeAlert(**alert) for alert in fused.alerts]
    state.missing_inputs = missing_inputs

    fused_severity = max(state.final_fatigue_score, state.burnout_risk_index)
    if fused_severity > state.thresholds.fatigued_max:
        state.state_label = StateLabel.BURNOUT_RISK
    elif fused_severity > state.thresholds.high_load_max:
        state.state_label = StateLabel.FATIGUED
    elif fused_severity > state.thresholds.normal_max:
        state.state_label = StateLabel.HIGH_LOAD
    else:
        state.state_label = StateLabel.NORMAL

    if eye_state.warnings:
        state.insights.extend([note for note in eye_state.warnings if note not in state.insights])
    if missing_inputs:
        state.insights.extend([note for note in missing_inputs if note not in state.insights])

    if notification is None and state.alerts and state.alert_level in {"moderate", "strong"}:
        first_alert = state.alerts[0]
        notification = NotificationMessage(
            title=first_alert.title,
            body=first_alert.message,
            severity=first_alert.severity,
            kind="multimodal_alert",
            created_at=state.timestamp,
        )
        state.notification = notification

    if recent_windows:
        await insert_feature_window(
            db,
            user_id,
            window_start=recent_windows[0].timestamp.isoformat(),
            window_end=recent_windows[-1].timestamp.isoformat(),
            features=features,
        )

    prediction_id = await insert_prediction(
        db,
        user_id,
        {
            "timestamp": state.timestamp,
            "state_label": state.state_label.value,
            "fatigue_score": state.fatigue_score,
            "load_score": state.load_score,
            "confidence": state.confidence,
            "confidence_level": state.confidence_level,
            "confidence_components": state.confidence_components,
            "model_maturity": state.model_maturity,
            "burnout_risk_index": state.burnout_risk_index,
            "p_fatigue": state.p_fatigue,
            "p_high_load": state.p_high_load,
            "instant_fatigue_score": state.instant_fatigue_score,
            "instant_load_score": state.instant_load_score,
            "smoothed_fatigue_score": state.smoothed_fatigue_score,
            "smoothed_load_score": state.smoothed_load_score,
            "eye_fatigue_score": state.eye_fatigue_score,
            "drowsy_flag": state.drowsy_flag,
            "final_fatigue_score": state.final_fatigue_score,
            "alert_level": state.alert_level,
            "alerts": [item.model_dump() for item in state.alerts],
            "missing_inputs": state.missing_inputs,
            "explanation": [item.model_dump() for item in state.explanation],
            "insights": state.insights,
            "plain_summary": state.plain_summary,
            "thresholds": state.thresholds.model_dump(),
            "today_summary": state.today_summary.model_dump(),
        },
    )
    if notification:
        await insert_notification(db, user_id, notification)

    await _maybe_emit_companion_messages(db, user_id, state, profile, normalized_payload.active_domain)

    response_payload = state.model_dump()
    response_payload["type"] = "LIVE_STATE"
    await manager.broadcast(user_id, response_payload)
    return IngestResponse(state=state)


@router.get("/state/latest", response_model=Optional[LiveState])
async def get_latest_state(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    await _ensure_welcome_messages(db, user_id)
    latest = await fetch_latest_prediction(db, user_id)
    if not latest:
        return None
    latest["current_features"] = await fetch_latest_feature_window(db, user_id)
    latest["history_minutes"] = ENGINE.build_history_strip(user_id)
    if not latest.get("today_summary"):
        latest["today_summary"] = (await _make_today_summary(db, user_id)).model_dump()
    return LiveState(**latest)


@router.get("/metrics/history", response_model=HistoryResponse)
async def get_history(
    user_id: str = Query("default"),
    limit: int = Query(90, ge=10, le=240),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await fetch_prediction_history(db, user_id, limit)
    return HistoryResponse(user_id=user_id, points=[HistoryPoint(**row) for row in rows])


@router.get("/burnout/trend", response_model=BurnoutTrendResponse)
async def get_burnout_trend(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    snapshot = await fetch_daily_burnout_snapshot(db, user_id)
    insights = []
    if snapshot["total_high_load_minutes_today"] >= 90:
        insights.append("Today already had a long heavy stretch.")
    if snapshot["consecutive_high_days"] >= 2:
        insights.append("You have been carrying a lot for more than one day.")
    if not insights:
        insights.append("There is no strong overload pattern across days yet.")
    return BurnoutTrendResponse(user_id=user_id, insights=insights, **snapshot)


@router.get("/notifications", response_model=NotificationFeedResponse)
async def get_notifications(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    notifications = await fetch_notifications(db, user_id)
    return NotificationFeedResponse(user_id=user_id, notifications=notifications)


@router.post("/video-sessions", response_model=VideoSessionRecord)
async def log_video_session(
    payload: VideoSessionPayload,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    record_id = await insert_video_session(db, user_id, payload)
    return VideoSessionRecord(
        id=record_id,
        user_id=user_id,
        platform=payload.platform,
        duration_min=payload.duration_min,
        timestamp=payload.timestamp.isoformat(),
        source=payload.source,
        in_focus_block=payload.in_focus_block,
        note=payload.note,
    )


@router.get("/video-sessions", response_model=VideoSessionListResponse)
async def list_video_sessions(
    user_id: str = Query("default"),
    limit: int = Query(30, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await fetch_video_sessions(db, user_id, limit=limit)
    return VideoSessionListResponse(
        user_id=user_id,
        sessions=[
            VideoSessionRecord(
                id=row["id"],
                user_id=row["user_id"],
                platform=row["platform"],
                duration_min=row["duration_min"],
                timestamp=row["timestamp"],
                source=row["source"],
                in_focus_block=bool(row["in_focus_block"]),
                note=row.get("note"),
            )
            for row in rows
        ],
    )


@router.get("/video-sessions/summary", response_model=VideoSummaryResponse)
async def get_video_summary(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    summary = await fetch_video_summary(db, user_id)
    return VideoSummaryResponse(user_id=user_id, **summary)


@router.get("/telemetry/recent", response_model=TelemetryRecentResponse)
async def telemetry_recent(
    user_id: str = Query("default"),
    limit: int = Query(30, ge=5, le=240),
    db: aiosqlite.Connection = Depends(get_db),
):
    points = await fetch_recent_telemetry(db, user_id, limit=limit)
    return TelemetryRecentResponse(user_id=user_id, points=[TelemetryPoint(**point) for point in points])


@router.post("/eye/metrics", response_model=EyeFatigueStateResponse)
async def ingest_eye_metrics(
    payload: EyeMetricsPayload,
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    result = PIPELINE.ingest_eye_metrics(
        user_id=user_id,
        ear=payload.ear,
        blink_rate_per_min=payload.blink_rate_per_min,
        closure_duration_s=payload.closure_duration_s,
        frame_rate=payload.frame_rate,
        timestamp=payload.timestamp,
        source=payload.source,
    )
    await insert_eye_observation(
        db,
        user_id,
        {
            "timestamp": result.timestamp,
            "source": result.source,
            "ear": result.ear,
            "blink_rate_per_min": result.blink_rate_per_min,
            "eye_closure_duration_s": result.eye_closure_duration_s,
            "eye_fatigue_score": result.eye_fatigue_score,
            "drowsy_flag": result.drowsy_flag,
            "warnings": result.warnings,
        },
    )
    return EyeFatigueStateResponse(user_id=user_id, **result.__dict__)


@router.get("/eye/latest", response_model=EyeFatigueStateResponse)
async def eye_latest(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    stored = await fetch_latest_eye_observation(db, user_id)
    if stored:
        return EyeFatigueStateResponse(user_id=user_id, **stored)
    fallback = PIPELINE.latest_eye_state(user_id)
    return EyeFatigueStateResponse(user_id=user_id, **fallback.__dict__)


@router.get("/app-breakdown", response_model=AppBreakdownResponse)
async def app_breakdown(
    user_id: str = Query("default"),
    limit: int = Query(120, ge=10, le=720),
    db: aiosqlite.Connection = Depends(get_db),
):
    profile_record = await fetch_profile(db, user_id)
    telemetry_points = await fetch_recent_telemetry(db, user_id, limit=limit)
    analysis = PIPELINE.analyze_app_usage(telemetry_points, profile_record["profile"])
    return AppBreakdownResponse(user_id=user_id, **analysis)


@router.delete("/metrics/reset")
async def reset_metrics(
    user_id: str = Query("default"),
    db: aiosqlite.Connection = Depends(get_db),
):
    await reset_user_data(db, user_id)
    return {"ok": True}


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket, user_id: str = "default"):
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

