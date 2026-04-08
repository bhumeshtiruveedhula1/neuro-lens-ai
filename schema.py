from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class StateLabel(str, Enum):
    NORMAL = "Normal"
    HIGH_LOAD = "High Load"
    FATIGUED = "Fatigued"
    BURNOUT_RISK = "Burnout Risk"


class BreakStyle(str, Enum):
    SHORT_SPRINTS = "short_sprints"
    BALANCED = "balanced"
    LONG_FOCUS = "long_focus"


class AppLists(BaseModel):
    focus: List[str] = Field(default_factory=list)
    distraction: List[str] = Field(default_factory=list)
    communication: List[str] = Field(default_factory=list)
    entertainment: List[str] = Field(default_factory=list)


class OnboardingProfile(BaseModel):
    baseline_fatigue_week: float = Field(35, ge=0, le=100)
    baseline_stress_week: float = Field(35, ge=0, le=100)
    current_fatigue: float = Field(30, ge=0, le=100)
    current_stress: float = Field(30, ge=0, le=100)
    deep_focus_capacity_min: int = Field(75, ge=15, le=240)
    preferred_work_cycle_min: int = Field(50, ge=15, le=180)
    focus_capacity_minutes: int = Field(75, ge=15, le=240)
    break_style: BreakStyle = BreakStyle.BALANCED
    user_target_hours: float = Field(6.0, ge=1, le=16)
    context_switch_sensitivity: float = Field(50, ge=0, le=100)
    avg_sleep_hours: float = Field(7.5, ge=3, le=12)
    last_night_sleep_hours: float = Field(7.0, ge=0, le=14)
    workday_start_hour: float = Field(9.0, ge=0, le=23.99)
    workday_end_hour: float = Field(18.0, ge=0, le=23.99)
    learning_period_days: int = Field(7, ge=3, le=14)
    alerts_enabled: bool = True
    focus_apps: List[str] = Field(default_factory=list)
    distraction_apps: List[str] = Field(default_factory=list)
    communication_apps: List[str] = Field(default_factory=list)
    entertainment_apps: List[str] = Field(default_factory=list)
    first_week_started_at: Optional[str] = None
    onboarding_complete: bool = False

    @field_validator(
        "focus_apps",
        "distraction_apps",
        "communication_apps",
        "entertainment_apps",
        mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.replace("\n", ",").split(",")]
            return [item for item in parts if item]
        return [str(item).strip().lower() for item in value if str(item).strip()]


class ProfileResponse(BaseModel):
    user_id: str
    profile: OnboardingProfile
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MinuteTelemetryPayload(BaseModel):
    timestamp: Optional[datetime] = None
    window_duration_s: int = Field(60, ge=30, le=120)
    app_name: str = Field("browser")
    active_domain: Optional[str] = None
    active_path: Optional[str] = None
    page_title: Optional[str] = None
    key_count: int = Field(0, ge=0)
    character_count: int = Field(0, ge=0)
    backspace_count: int = Field(0, ge=0)
    mean_key_hold: float = Field(0, ge=0)
    std_key_hold: float = Field(0, ge=0)
    key_hold_samples: int = Field(0, ge=0)
    mean_interkey_latency: float = Field(0, ge=0)
    std_interkey_latency: float = Field(0, ge=0)
    interkey_samples: int = Field(0, ge=0)
    typing_active_seconds: float = Field(0, ge=0)
    active_seconds: float = Field(0, ge=0)
    idle_seconds: float = Field(0, ge=0)
    idle_bursts: int = Field(0, ge=0)
    tab_switches: int = Field(0, ge=0)
    window_switches: int = Field(0, ge=0)
    short_video_seconds: float = Field(0, ge=0)
    short_video_sessions: int = Field(0, ge=0)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _default_timestamp(cls, value):
        return value or datetime.now(UTC)


class ExplanationItem(BaseModel):
    feature: str
    direction: str
    impact: float
    reason: str


class NotificationMessage(BaseModel):
    title: str
    body: str
    severity: str
    kind: str
    created_at: str


class ThresholdProfile(BaseModel):
    normal_max: float = 40.0
    high_load_max: float = 65.0
    fatigued_max: float = 80.0
    reason: str = "Using default thresholds while I learn your rhythm."


class TodaySummary(BaseModel):
    deep_focus_minutes: float = 0.0
    high_fatigue_minutes: float = 0.0
    breaks_taken: int = 0


class LiveState(BaseModel):
    user_id: str
    timestamp: str
    state_label: StateLabel
    fatigue_score: float
    load_score: float
    confidence: float
    model_maturity: float
    burnout_risk_index: float
    p_fatigue: float
    p_high_load: float
    explanation: List[ExplanationItem] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    current_features: Dict[str, float] = Field(default_factory=dict)
    history_minutes: List[Dict[str, Any]] = Field(default_factory=list)
    notification: Optional[NotificationMessage] = None
    thresholds: ThresholdProfile = Field(default_factory=ThresholdProfile)
    plain_summary: str = "You are in a normal range."
    today_summary: TodaySummary = Field(default_factory=TodaySummary)


class IngestResponse(BaseModel):
    ok: bool = True
    state: LiveState


class HistoryPoint(BaseModel):
    timestamp: str
    fatigue_score: float
    load_score: float
    confidence: float
    state_label: StateLabel


class HistoryResponse(BaseModel):
    user_id: str
    points: List[HistoryPoint]


class BurnoutTrendResponse(BaseModel):
    user_id: str
    burnout_risk_index: float
    total_high_load_minutes_today: float
    consecutive_high_days: int
    insights: List[str] = Field(default_factory=list)


class NotificationFeedResponse(BaseModel):
    user_id: str
    notifications: List[NotificationMessage]


class ModelStatusResponse(BaseModel):
    status: str
    model_type: str
    model_version: str
    feature_count: int
    backend: str
    explanation_mode: str


class SelfReportPayload(BaseModel):
    report_type: Literal["check_in", "end_of_day", "support", "onboarding", "break_feedback"] = "check_in"
    fatigue_level: Optional[float] = Field(default=None, ge=0, le=10)
    stress_level: Optional[float] = Field(default=None, ge=0, le=10)
    fogginess: Optional[float] = Field(default=None, ge=0, le=10)
    work_balance: Optional[Literal["too_much", "just_right", "too_little"]] = None
    break_preference: Optional[Literal["fewer", "just_right", "more"]] = None
    severe_stress_event: bool = False
    note: Optional[str] = None
    related_window_end: Optional[str] = None
    answer_values: Dict[str, Any] = Field(default_factory=dict)


class SelfReportRecord(BaseModel):
    id: int
    user_id: str
    timestamp: str
    report_type: str
    fatigue_level: Optional[float] = None
    stress_level: Optional[float] = None
    fogginess: Optional[float] = None
    work_balance: Optional[str] = None
    break_preference: Optional[str] = None
    severe_stress_event: bool = False
    note: Optional[str] = None
    related_window_end: Optional[str] = None
    answer_values: Dict[str, Any] = Field(default_factory=dict)


class SelfReportResponse(BaseModel):
    ok: bool = True
    report: SelfReportRecord


class ChatQuickReply(BaseModel):
    id: str
    label: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    id: str
    role: Literal["assistant", "user", "system"]
    kind: str
    text: str
    created_at: str
    quick_replies: List[ChatQuickReply] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    unread: bool = False


class ChatThreadResponse(BaseModel):
    user_id: str
    messages: List[ChatMessage]
    unread_count: int = 0


class ChatUserMessagePayload(BaseModel):
    text: Optional[str] = None
    quick_reply_action: Optional[str] = None
    quick_reply_payload: Dict[str, Any] = Field(default_factory=dict)


class ChatSendResponse(BaseModel):
    ok: bool = True
    user_message: Optional[ChatMessage] = None
    assistant_messages: List[ChatMessage] = Field(default_factory=list)
    suggested_self_report: Optional[SelfReportPayload] = None


class CalibrationLabelRecord(BaseModel):
    id: int
    user_id: str
    timestamp: str
    label_kind: Literal["confirmed_high_fatigue", "confirmed_safe", "severe_stress_event"]
    label_value: float
    main_model_score: float
    prediction_id: Optional[int] = None
    source_report_id: Optional[int] = None


class CalibrationStatusResponse(BaseModel):
    user_id: str
    thresholds: ThresholdProfile
    label_count: int
    strong_label_count: int
    notes: List[str] = Field(default_factory=list)
