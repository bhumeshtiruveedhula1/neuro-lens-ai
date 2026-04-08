from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from schema import (
    ChatMessage,
    MinuteTelemetryPayload,
    NotificationMessage,
    OnboardingProfile,
    SelfReportPayload,
)

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "neurolens.db"


async def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telemetry_minute (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_user_time
                ON telemetry_minute(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS feature_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                features_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_feature_windows_user_time
                ON feature_windows(user_id, window_end DESC);

            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                state_label TEXT NOT NULL,
                fatigue_score REAL NOT NULL,
                load_score REAL NOT NULL,
                confidence REAL NOT NULL,
                model_maturity REAL NOT NULL,
                burnout_risk_index REAL NOT NULL,
                p_fatigue REAL NOT NULL,
                p_high_load REAL NOT NULL,
                explanations_json TEXT NOT NULL,
                insights_json TEXT NOT NULL,
                plain_summary TEXT NOT NULL DEFAULT '',
                thresholds_json TEXT NOT NULL DEFAULT '{}',
                today_summary_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_predictions_user_time
                ON predictions(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                severity TEXT NOT NULL,
                kind TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_user_time
                ON notifications(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS self_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                report_type TEXT NOT NULL,
                fatigue_level REAL,
                stress_level REAL,
                fogginess REAL,
                work_balance TEXT,
                break_preference TEXT,
                severe_stress_event INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                related_window_end TEXT,
                answer_values_json TEXT NOT NULL DEFAULT '{}',
                prediction_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_self_reports_user_time
                ON self_reports(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS calibration_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                label_kind TEXT NOT NULL,
                label_value REAL NOT NULL,
                main_model_score REAL NOT NULL,
                prediction_id INTEGER,
                source_report_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_calibration_user_time
                ON calibration_labels(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS chat_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                quick_replies_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                unread INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_chat_user_time
                ON chat_events(user_id, created_at DESC);
            """
        )
        await db.commit()
        logger.info("Database initialized at %s", DB_PATH)


DEFAULT_PROFILE = OnboardingProfile()


async def _ensure_prediction_columns(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(predictions)")
    cols = {row["name"] for row in await cursor.fetchall()}
    additions = {
        "plain_summary": "ALTER TABLE predictions ADD COLUMN plain_summary TEXT NOT NULL DEFAULT ''",
        "thresholds_json": "ALTER TABLE predictions ADD COLUMN thresholds_json TEXT NOT NULL DEFAULT '{}'",
        "today_summary_json": "ALTER TABLE predictions ADD COLUMN today_summary_json TEXT NOT NULL DEFAULT '{}'",
    }
    for name, statement in additions.items():
        if name not in cols:
            await db.execute(statement)
    await db.commit()


async def fetch_profile(db: aiosqlite.Connection, user_id: str) -> dict:
    cursor = await db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row:
        return {
            "user_id": user_id,
            "profile": DEFAULT_PROFILE,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "user_id": user_id,
        "profile": OnboardingProfile(**json.loads(row["profile_json"])),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def upsert_profile(db: aiosqlite.Connection, user_id: str, profile: OnboardingProfile) -> dict:
    now = datetime.now(UTC).isoformat()
    if not profile.first_week_started_at:
        profile.first_week_started_at = now
    await db.execute(
        """
        INSERT INTO user_profiles (user_id, profile_json, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            profile_json = excluded.profile_json,
            updated_at = excluded.updated_at
        """,
        (user_id, profile.model_dump_json(), now, now),
    )
    await db.commit()
    return await fetch_profile(db, user_id)


async def insert_minute_telemetry(db: aiosqlite.Connection, user_id: str, payload: MinuteTelemetryPayload) -> None:
    await db.execute(
        "INSERT INTO telemetry_minute (user_id, timestamp, payload_json) VALUES (?, ?, ?)",
        (user_id, payload.timestamp.isoformat(), payload.model_dump_json()),
    )
    await db.commit()


async def insert_feature_window(
    db: aiosqlite.Connection,
    user_id: str,
    window_start: str,
    window_end: str,
    features: Dict[str, float],
) -> int:
    cursor = await db.execute(
        "INSERT INTO feature_windows (user_id, window_start, window_end, features_json) VALUES (?, ?, ?, ?)",
        (user_id, window_start, window_end, json.dumps(features)),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def insert_prediction(
    db: aiosqlite.Connection,
    user_id: str,
    state: Dict[str, Any],
) -> int:
    await _ensure_prediction_columns(db)
    cursor = await db.execute(
        """
        INSERT INTO predictions (
            user_id, timestamp, state_label, fatigue_score, load_score, confidence,
            model_maturity, burnout_risk_index, p_fatigue, p_high_load,
            explanations_json, insights_json, plain_summary, thresholds_json, today_summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            state["timestamp"],
            state["state_label"],
            state["fatigue_score"],
            state["load_score"],
            state["confidence"],
            state["model_maturity"],
            state["burnout_risk_index"],
            state["p_fatigue"],
            state["p_high_load"],
            json.dumps(state["explanation"]),
            json.dumps(state["insights"]),
            state.get("plain_summary", ""),
            json.dumps(state.get("thresholds", {})),
            json.dumps(state.get("today_summary", {})),
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def insert_notification(db: aiosqlite.Connection, user_id: str, notification: NotificationMessage) -> None:
    await db.execute(
        """
        INSERT INTO notifications (user_id, created_at, title, body, severity, kind)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            notification.created_at,
            notification.title,
            notification.body,
            notification.severity,
            notification.kind,
        ),
    )
    await db.commit()


async def insert_chat_event(db: aiosqlite.Connection, user_id: str, message: ChatMessage) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO chat_events (
            id, user_id, created_at, role, kind, text,
            quick_replies_json, metadata_json, unread
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message.id,
            user_id,
            message.created_at,
            message.role,
            message.kind,
            message.text,
            json.dumps([reply.model_dump() for reply in message.quick_replies]),
            json.dumps(message.metadata),
            int(message.unread),
        ),
    )
    await db.commit()


async def fetch_chat_events(db: aiosqlite.Connection, user_id: str, limit: int = 50) -> List[ChatMessage]:
    cursor = await db.execute(
        """
        SELECT * FROM chat_events
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    events = []
    for row in reversed(rows):
        events.append(
            ChatMessage(
                id=row["id"],
                role=row["role"],
                kind=row["kind"],
                text=row["text"],
                created_at=row["created_at"],
                quick_replies=json.loads(row["quick_replies_json"]),
                metadata=json.loads(row["metadata_json"]),
                unread=bool(row["unread"]),
            )
        )
    return events


async def mark_chat_read(db: aiosqlite.Connection, user_id: str) -> None:
    await db.execute("UPDATE chat_events SET unread = 0 WHERE user_id = ? AND role = 'assistant'", (user_id,))
    await db.commit()


async def fetch_unread_chat_count(db: aiosqlite.Connection, user_id: str) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) AS count FROM chat_events WHERE user_id = ? AND unread = 1 AND role = 'assistant'",
        (user_id,),
    )
    row = await cursor.fetchone()
    return int(row["count"]) if row else 0


async def insert_self_report(
    db: aiosqlite.Connection,
    user_id: str,
    report: SelfReportPayload,
    prediction_id: Optional[int] = None,
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO self_reports (
            user_id, timestamp, report_type, fatigue_level, stress_level, fogginess,
            work_balance, break_preference, severe_stress_event, note,
            related_window_end, answer_values_json, prediction_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            datetime.now(UTC).isoformat(),
            report.report_type,
            report.fatigue_level,
            report.stress_level,
            report.fogginess,
            report.work_balance,
            report.break_preference,
            int(report.severe_stress_event),
            report.note,
            report.related_window_end,
            json.dumps(report.answer_values),
            prediction_id,
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def fetch_self_reports(db: aiosqlite.Connection, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT * FROM self_reports
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [
        {
            **dict(row),
            "severe_stress_event": bool(row["severe_stress_event"]),
            "answer_values": json.loads(row["answer_values_json"]),
        }
        for row in rows
    ]


async def insert_calibration_label(
    db: aiosqlite.Connection,
    user_id: str,
    label_kind: str,
    label_value: float,
    main_model_score: float,
    prediction_id: Optional[int],
    source_report_id: Optional[int],
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO calibration_labels (
            user_id, timestamp, label_kind, label_value,
            main_model_score, prediction_id, source_report_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            datetime.now(UTC).isoformat(),
            label_kind,
            label_value,
            main_model_score,
            prediction_id,
            source_report_id,
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def fetch_calibration_labels(db: aiosqlite.Connection, user_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT * FROM calibration_labels
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def fetch_recent_feature_windows(db: aiosqlite.Connection, user_id: str, limit: int = 120) -> List[Dict[str, float]]:
    cursor = await db.execute(
        """
        SELECT features_json FROM feature_windows
        WHERE user_id = ?
        ORDER BY window_end DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [json.loads(row["features_json"]) for row in reversed(rows)]


async def fetch_prediction_count(db: aiosqlite.Connection, user_id: str) -> int:
    cursor = await db.execute("SELECT COUNT(*) AS count FROM predictions WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return int(row["count"]) if row else 0


async def fetch_distinct_prediction_days(db: aiosqlite.Connection, user_id: str) -> int:
    cursor = await db.execute(
        "SELECT COUNT(DISTINCT substr(timestamp, 1, 10)) AS count FROM predictions WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return int(row["count"]) if row else 0


async def fetch_latest_prediction(db: aiosqlite.Connection, user_id: str) -> Optional[Dict[str, Any]]:
    await _ensure_prediction_columns(db)
    cursor = await db.execute(
        """
        SELECT * FROM predictions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "user_id": user_id,
        "timestamp": row["timestamp"],
        "state_label": row["state_label"],
        "fatigue_score": row["fatigue_score"],
        "load_score": row["load_score"],
        "confidence": row["confidence"],
        "model_maturity": row["model_maturity"],
        "burnout_risk_index": row["burnout_risk_index"],
        "p_fatigue": row["p_fatigue"],
        "p_high_load": row["p_high_load"],
        "explanation": json.loads(row["explanations_json"]),
        "insights": json.loads(row["insights_json"]),
        "plain_summary": row["plain_summary"],
        "thresholds": json.loads(row["thresholds_json"]),
        "today_summary": json.loads(row["today_summary_json"]),
    }


async def fetch_latest_feature_window(db: aiosqlite.Connection, user_id: str) -> Dict[str, Any]:
    cursor = await db.execute(
        """
        SELECT features_json FROM feature_windows
        WHERE user_id = ?
        ORDER BY window_end DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = await cursor.fetchone()
    return json.loads(row["features_json"]) if row else {}


async def fetch_prediction_history(db: aiosqlite.Connection, user_id: str, limit: int = 90) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT timestamp, fatigue_score, load_score, confidence, state_label
        FROM predictions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in reversed(rows)]


async def fetch_notifications(db: aiosqlite.Connection, user_id: str, limit: int = 20) -> List[NotificationMessage]:
    cursor = await db.execute(
        """
        SELECT created_at, title, body, severity, kind
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [
        NotificationMessage(
            created_at=row["created_at"],
            title=row["title"],
            body=row["body"],
            severity=row["severity"],
            kind=row["kind"],
        )
        for row in rows
    ]


async def fetch_daily_burnout_snapshot(db: aiosqlite.Connection, user_id: str) -> Dict[str, Any]:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    cursor = await db.execute(
        """
        SELECT
            COALESCE(MAX(burnout_risk_index), 0) AS max_burnout,
            COALESCE(SUM(CASE WHEN load_score >= 40 OR fatigue_score >= 40 THEN 5 ELSE 0 END), 0) AS high_load_minutes
        FROM predictions
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ?
        """,
        (user_id, today),
    )
    today_row = await cursor.fetchone()

    cursor = await db.execute(
        """
        SELECT day_key, day_load
        FROM (
            SELECT
                substr(timestamp, 1, 10) AS day_key,
                MAX(MAX(load_score, fatigue_score, burnout_risk_index)) AS day_load
            FROM predictions
            WHERE user_id = ?
            GROUP BY substr(timestamp, 1, 10)
            ORDER BY day_key DESC
            LIMIT 14
        )
        ORDER BY day_key DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    consecutive_high_days = 0
    for row in rows:
        if row["day_load"] >= 65:
            consecutive_high_days += 1
        else:
            break

    return {
        "burnout_risk_index": float(today_row["max_burnout"] or 0.0) if today_row else 0.0,
        "total_high_load_minutes_today": float(today_row["high_load_minutes"] or 0.0) if today_row else 0.0,
        "consecutive_high_days": consecutive_high_days,
    }


async def fetch_today_summary(db: aiosqlite.Connection, user_id: str) -> Dict[str, float]:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    cursor = await db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN state_label = 'Normal' AND load_score <= 25 AND fatigue_score <= 25 THEN 5 ELSE 0 END), 0) AS deep_focus_minutes,
            COALESCE(SUM(CASE WHEN state_label IN ('Fatigued', 'Burnout Risk') THEN 5 ELSE 0 END), 0) AS high_fatigue_minutes
        FROM predictions
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ?
        """,
        (user_id, today),
    )
    score_row = await cursor.fetchone()

    cursor = await db.execute(
        """
        SELECT COUNT(*) AS breaks_taken
        FROM telemetry_minute
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ? AND payload_json LIKE '%"idle_seconds":%'
        """,
        (user_id, today),
    )
    telemetry_row = await cursor.fetchone()
    return {
        "deep_focus_minutes": float(score_row["deep_focus_minutes"] or 0.0) if score_row else 0.0,
        "high_fatigue_minutes": float(score_row["high_fatigue_minutes"] or 0.0) if score_row else 0.0,
        "breaks_taken": float(telemetry_row["breaks_taken"] or 0.0) if telemetry_row else 0.0,
    }


async def fetch_prompt_count_for_day(db: aiosqlite.Connection, user_id: str) -> int:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    cursor = await db.execute(
        """
        SELECT COUNT(*) AS count
        FROM chat_events
        WHERE user_id = ? AND role = 'assistant' AND substr(created_at, 1, 10) = ?
          AND kind IN ('question', 'check_in', 'break_prompt')
        """,
        (user_id, today),
    )
    row = await cursor.fetchone()
    return int(row["count"]) if row else 0


async def reset_user_data(db: aiosqlite.Connection, user_id: str) -> None:
    for table in (
        "telemetry_minute",
        "feature_windows",
        "predictions",
        "notifications",
        "self_reports",
        "calibration_labels",
        "chat_events",
        "user_profiles",
    ):
        await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    await db.commit()
