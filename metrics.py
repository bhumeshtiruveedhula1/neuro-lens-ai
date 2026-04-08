from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

import aiosqlite
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from calibration import derive_thresholds
from cognitive_engine import ENGINE
from companion import build_first_week_prompt, build_proactive_message, build_welcome_sequence, respond_to_user_message
from database import (
    fetch_calibration_labels,
    fetch_chat_events,
    fetch_daily_burnout_snapshot,
    fetch_distinct_prediction_days,
    fetch_latest_feature_window,
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
    get_db,
    insert_calibration_label,
    insert_chat_event,
    insert_feature_window,
    insert_minute_telemetry,
    insert_notification,
    insert_prediction,
    insert_self_report,
    mark_chat_read,
    reset_user_data,
    upsert_profile,
)
from schema import (
    BurnoutTrendResponse,
    CalibrationStatusResponse,
    ChatMessage,
    ChatSendResponse,
    ChatThreadResponse,
    ChatUserMessagePayload,
    HistoryPoint,
    HistoryResponse,
    IngestResponse,
    LiveState,
    MinuteTelemetryPayload,
    NotificationFeedResponse,
    OnboardingProfile,
    ProfileResponse,
    SelfReportPayload,
    SelfReportRecord,
    SelfReportResponse,
    TodaySummary,
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


async def _build_burnout_risk_index(db: aiosqlite.Connection, user_id: str, fatigue_score: float, load_score: float) -> tuple[float, list[str]]:
    snapshot = await fetch_daily_burnout_snapshot(db, user_id)
    high_minutes = snapshot["total_high_load_minutes_today"]
    consecutive_days = snapshot["consecutive_high_days"]
    base = max(snapshot["burnout_risk_index"], fatigue_score * 0.65 + load_score * 0.35)
    risk = min(100.0, base * 0.55 + min(high_minutes / 3.0, 25.0) + consecutive_days * 8.0)

    insights = []
    if high_minutes >= 90:
        insights.append("You spent a lot of today in a heavy mental zone.")
    if consecutive_days >= 2:
        insights.append("This pattern has been showing up for more than one day.")
    if not insights:
        insights.append("Today’s risk is still mostly based on your latest work pattern.")
    return round(risk, 2), insights


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

    await insert_minute_telemetry(db, user_id, payload)
    ENGINE.append_window(user_id, payload)

    recent_windows = ENGINE.get_recent_windows(user_id, limit=5)
    rolling_reference = await fetch_recent_feature_windows(db, user_id, limit=120)
    features = ENGINE.build_feature_vector(user_id, profile, recent_windows, rolling_reference)

    prediction_count = await fetch_prediction_count(db, user_id)
    distinct_days = await fetch_distinct_prediction_days(db, user_id)
    maturity = ENGINE.model_maturity(profile, prediction_count, distinct_days)

    calibration_snapshot = derive_thresholds(await fetch_calibration_labels(db, user_id))
    rough_risk, burnout_insights = await _build_burnout_risk_index(db, user_id, 0, 0)
    today_summary = await _make_today_summary(db, user_id)

    state, notification, _ = ENGINE.derive_state(
        user_id=user_id,
        timestamp=payload.timestamp,
        profile=profile,
        features=features,
        maturity=maturity,
        burnout_risk_index=rough_risk,
        thresholds=calibration_snapshot.thresholds,
        today_summary=today_summary,
    )
    final_risk, burnout_insights = await _build_burnout_risk_index(db, user_id, state.fatigue_score, state.load_score)
    state.burnout_risk_index = final_risk
    state.thresholds = calibration_snapshot.thresholds
    state.insights.extend([item for item in burnout_insights if item not in state.insights])
    state.insights.extend([item for item in calibration_snapshot.notes if item not in state.insights])
    state.history_minutes = ENGINE.build_history_strip(user_id)
    state.today_summary = await _make_today_summary(db, user_id)

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
            "model_maturity": state.model_maturity,
            "burnout_risk_index": state.burnout_risk_index,
            "p_fatigue": state.p_fatigue,
            "p_high_load": state.p_high_load,
            "explanation": [item.model_dump() for item in state.explanation],
            "insights": state.insights,
            "plain_summary": state.plain_summary,
            "thresholds": state.thresholds.model_dump(),
            "today_summary": state.today_summary.model_dump(),
        },
    )
    if notification:
        await insert_notification(db, user_id, notification)

    await _maybe_emit_companion_messages(db, user_id, state, profile, payload.active_domain)

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
