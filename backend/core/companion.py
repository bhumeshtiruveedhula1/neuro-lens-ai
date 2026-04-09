from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional, Tuple

from backend.core.schema import (
    ChatMessage,
    ChatQuickReply,
    ChatUserMessagePayload,
    LiveState,
    OnboardingProfile,
    SelfReportPayload,
)

SEVERE_TERMS = (
    "breakdown",
    "terrible",
    "can't do this",
    "cannot do this",
    "i feel awful",
    "panic",
    "burned out",
    "burnt out",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _assistant_message(
    message_id: str,
    text: str,
    *,
    kind: str = "support",
    quick_replies: Optional[List[ChatQuickReply]] = None,
    unread: bool = True,
    metadata: Optional[Dict] = None,
) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        role="assistant",
        kind=kind,
        text=text,
        created_at=_now_iso(),
        quick_replies=quick_replies or [],
        unread=unread,
        metadata=metadata or {},
    )


def build_welcome_sequence() -> List[ChatMessage]:
    return [
        _assistant_message(
            "welcome-1",
            "Hi, I'm NeuroLens. I'll quietly learn how you work and help you protect your energy.",
            kind="welcome",
        ),
        _assistant_message(
            "welcome-2",
            "I watch how you work in the background, and I try to tell when your brain is getting tired or overloaded, so you can take care of yourself.",
            kind="welcome",
            quick_replies=[
                ChatQuickReply(id="lets-go", label="Sounds good", action="ack_welcome"),
                ChatQuickReply(id="tell-me-more", label="Tell me more", action="ask_about_learning"),
            ],
        ),
    ]


def build_first_week_prompt(profile: OnboardingProfile, recent_app: Optional[str], prompts_today: int) -> Optional[ChatMessage]:
    if prompts_today >= 4:
        return None

    if not profile.onboarding_complete:
        return _assistant_message(
            "first-week-rhythm",
            "What work rhythm feels best to you?",
            kind="question",
            quick_replies=[
                ChatQuickReply(id="sprints", label="Short sprints", action="set_break_style", payload={"break_style": "short_sprints"}),
                ChatQuickReply(id="balanced", label="A mix", action="set_break_style", payload={"break_style": "balanced"}),
                ChatQuickReply(id="deep", label="Long focus blocks", action="set_break_style", payload={"break_style": "long_focus"}),
            ],
        )

    if recent_app and "youtube" in recent_app.lower():
        return _assistant_message(
            "classify-youtube",
            "Is YouTube usually for work or for relaxing?",
            kind="question",
            quick_replies=[
                ChatQuickReply(id="yt-work", label="Mostly work", action="classify_app", payload={"app": "youtube", "bucket": "focus"}),
                ChatQuickReply(id="yt-relax", label="Mostly relaxing", action="classify_app", payload={"app": "youtube", "bucket": "distraction"}),
            ],
        )

    return _assistant_message(
        "quick-feel-check",
        "Right now, how mentally tired do you feel?",
        kind="question",
        quick_replies=[
            ChatQuickReply(id="fresh", label="0-2", action="self_report_fatigue", payload={"fatigue_level": 2}),
            ChatQuickReply(id="mid", label="3-6", action="self_report_fatigue", payload={"fatigue_level": 5}),
            ChatQuickReply(id="drained", label="7-10", action="self_report_fatigue", payload={"fatigue_level": 8}),
        ],
    )


def build_proactive_message(live_state: LiveState, prompts_today: int) -> Optional[ChatMessage]:
    if prompts_today >= 4:
        return None

    if live_state.notification and live_state.notification.kind in {"break", "task_switch"}:
        return _assistant_message(
            f"break-{live_state.timestamp}",
            "You've been pushing hard for a while. Want to take a 3-minute pause?",
            kind="break_prompt",
            quick_replies=[
                ChatQuickReply(id="break-now", label="Start 3-min break", action="start_break"),
                ChatQuickReply(id="not-now", label="Not now", action="dismiss_break"),
                ChatQuickReply(id="later", label="Remind me later", action="remind_later"),
            ],
        )

    if live_state.state_label.value in {"High Load", "Fatigued"} and live_state.confidence >= 0.62:
        return _assistant_message(
            f"checkin-{live_state.timestamp}",
            "On a scale from 0 to 10, how foggy does your mind feel right now?",
            kind="check_in",
            quick_replies=[
                ChatQuickReply(id="fog-low", label="0-2", action="self_report_fogginess", payload={"fogginess": 2}),
                ChatQuickReply(id="fog-mid", label="3-6", action="self_report_fogginess", payload={"fogginess": 5}),
                ChatQuickReply(id="fog-high", label="7-10", action="self_report_fogginess", payload={"fogginess": 8}),
            ],
        )

    if live_state.today_summary.breaks_taken >= 2 and live_state.today_summary.high_fatigue_minutes <= 25:
        return _assistant_message(
            f"positive-{live_state.timestamp}",
            "Nice, you took a break before you were totally drained. Small progress matters.",
            kind="encouragement",
            quick_replies=[],
        )

    return None


def respond_to_user_message(payload: ChatUserMessagePayload) -> Tuple[List[ChatMessage], Optional[SelfReportPayload], bool]:
    text = (payload.text or "").strip()
    lowered = text.lower()

    if any(term in lowered for term in SEVERE_TERMS):
        return (
            [
                _assistant_message(
                    f"support-{_now_iso()}",
                    "I'm really sorry you're feeling this way. You are not alone.",
                    kind="support",
                ),
                _assistant_message(
                    f"support-options-{_now_iso()}",
                    "Right now, the most important thing is to slow down and breathe. Do you want to take a longer break or stop for today?",
                    kind="support",
                    quick_replies=[
                        ChatQuickReply(id="support-break", label="Take a break", action="start_long_break"),
                        ChatQuickReply(id="support-end", label="End my workday", action="end_workday"),
                        ChatQuickReply(id="support-continue", label="I want to keep going", action="keep_going"),
                    ],
                ),
            ],
            SelfReportPayload(report_type="support", severe_stress_event=True, note=text),
            True,
        )

    if payload.quick_reply_action == "start_break":
        return (
            [_assistant_message(f"break-thanks-{_now_iso()}", "Good call. I'll stay quiet for a bit while you reset.", kind="encouragement", quick_replies=[])],
            None,
            False,
        )

    if payload.quick_reply_action == "remind_later":
        return (
            [_assistant_message(f"later-{_now_iso()}", "Okay. I'll check in again a little later.", kind="support", quick_replies=[])],
            None,
            False,
        )

    if payload.quick_reply_action in {"self_report_fatigue", "self_report_fogginess"}:
        answer = payload.quick_reply_payload or {}
        report = SelfReportPayload(
            report_type="check_in",
            fatigue_level=answer.get("fatigue_level"),
            fogginess=answer.get("fogginess"),
            answer_values=answer,
        )
        return (
            [_assistant_message(f"thanks-{_now_iso()}", "Thanks. That helps me learn what your tired days really feel like.", kind="support", quick_replies=[])],
            report,
            False,
        )

    return (
        [_assistant_message(f"echo-{_now_iso()}", "Thanks for telling me. I'm here with you, and I'll keep the next suggestion gentle.", kind="support", quick_replies=[])],
        None,
        False,
    )
