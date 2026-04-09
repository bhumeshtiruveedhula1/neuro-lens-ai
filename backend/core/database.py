from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.core.schema import (
    ChatMessage,
    MinuteTelemetryPayload,
    NotificationMessage,
    OnboardingProfile,
    SelfReportPayload,
    VideoSessionPayload,
)

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "neurolens.db"


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
                eye_fatigue_score REAL NOT NULL DEFAULT 0,
                drowsy_flag INTEGER NOT NULL DEFAULT 0,
                final_fatigue_score REAL NOT NULL DEFAULT 0,
                alert_level TEXT NOT NULL DEFAULT 'low',
                alerts_json TEXT NOT NULL DEFAULT '[]',
                missing_inputs_json TEXT NOT NULL DEFAULT '[]',
                instant_fatigue_score REAL NOT NULL DEFAULT 0,
                instant_load_score REAL NOT NULL DEFAULT 0,
                smoothed_fatigue_score REAL NOT NULL DEFAULT 0,
                smoothed_load_score REAL NOT NULL DEFAULT 0,
                confidence_level TEXT NOT NULL DEFAULT 'MEDIUM',
                confidence_components_json TEXT NOT NULL DEFAULT '{}',
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

            CREATE TABLE IF NOT EXISTS video_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                platform TEXT NOT NULL,
                duration_min REAL NOT NULL,
                source TEXT NOT NULL,
                in_focus_block INTEGER NOT NULL DEFAULT 0,
                note TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_video_user_time
                ON video_sessions(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS eye_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                ear REAL NOT NULL DEFAULT 0,
                blink_rate_per_min REAL NOT NULL DEFAULT 0,
                eye_closure_duration_s REAL NOT NULL DEFAULT 0,
                eye_fatigue_score REAL NOT NULL DEFAULT 0,
                drowsy_flag INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_eye_user_time
                ON eye_observations(user_id, timestamp DESC);

            CREATE TABLE IF NOT EXISTS user_feature_stats (
                user_id TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                rolling_mean REAL NOT NULL,
                rolling_std REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, feature_name)
            );
            CREATE INDEX IF NOT EXISTS idx_user_feature_stats_time
                ON user_feature_stats(user_id, updated_at DESC);
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
        "eye_fatigue_score": "ALTER TABLE predictions ADD COLUMN eye_fatigue_score REAL NOT NULL DEFAULT 0",
        "drowsy_flag": "ALTER TABLE predictions ADD COLUMN drowsy_flag INTEGER NOT NULL DEFAULT 0",
        "final_fatigue_score": "ALTER TABLE predictions ADD COLUMN final_fatigue_score REAL NOT NULL DEFAULT 0",
        "alert_level": "ALTER TABLE predictions ADD COLUMN alert_level TEXT NOT NULL DEFAULT 'low'",
        "alerts_json": "ALTER TABLE predictions ADD COLUMN alerts_json TEXT NOT NULL DEFAULT '[]'",
        "missing_inputs_json": "ALTER TABLE predictions ADD COLUMN missing_inputs_json TEXT NOT NULL DEFAULT '[]'",
        "instant_fatigue_score": "ALTER TABLE predictions ADD COLUMN instant_fatigue_score REAL NOT NULL DEFAULT 0",
        "instant_load_score": "ALTER TABLE predictions ADD COLUMN instant_load_score REAL NOT NULL DEFAULT 0",
        "smoothed_fatigue_score": "ALTER TABLE predictions ADD COLUMN smoothed_fatigue_score REAL NOT NULL DEFAULT 0",
        "smoothed_load_score": "ALTER TABLE predictions ADD COLUMN smoothed_load_score REAL NOT NULL DEFAULT 0",
        "confidence_level": "ALTER TABLE predictions ADD COLUMN confidence_level TEXT NOT NULL DEFAULT 'MEDIUM'",
        "confidence_components_json": "ALTER TABLE predictions ADD COLUMN confidence_components_json TEXT NOT NULL DEFAULT '{}'",
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
            eye_fatigue_score, drowsy_flag, final_fatigue_score, alert_level, alerts_json, missing_inputs_json,
            instant_fatigue_score, instant_load_score, smoothed_fatigue_score, smoothed_load_score,
            confidence_level, confidence_components_json,
            explanations_json, insights_json, plain_summary, thresholds_json, today_summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            state.get("eye_fatigue_score", 0.0),
            int(bool(state.get("drowsy_flag", False))),
            state.get("final_fatigue_score", state.get("fatigue_score", 0.0)),
            state.get("alert_level", "low"),
            json.dumps(state.get("alerts", [])),
            json.dumps(state.get("missing_inputs", [])),
            state.get("instant_fatigue_score", state.get("fatigue_score", 0.0)),
            state.get("instant_load_score", state.get("load_score", 0.0)),
            state.get("smoothed_fatigue_score", state.get("fatigue_score", 0.0)),
            state.get("smoothed_load_score", state.get("load_score", 0.0)),
            state.get("confidence_level", "MEDIUM"),
            json.dumps(state.get("confidence_components", {})),
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


async def upsert_personalization_stats(
    db: aiosqlite.Connection,
    user_id: str,
    feature_stats: Dict[str, Dict[str, float]],
) -> None:
    if not feature_stats:
        return
    now = datetime.now(UTC).isoformat()
    for feature_name, stats in feature_stats.items():
        await db.execute(
            """
            INSERT INTO user_feature_stats (user_id, feature_name, rolling_mean, rolling_std, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, feature_name) DO UPDATE SET
                rolling_mean = excluded.rolling_mean,
                rolling_std = excluded.rolling_std,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                feature_name,
                float(stats.get("rolling_mean", 0.0)),
                float(stats.get("rolling_std", 0.0)),
                now,
            ),
        )
    await db.commit()


async def fetch_burnout_inputs(db: aiosqlite.Connection, user_id: str, days: int = 14) -> Dict[str, float]:
    day_window = max(int(days), 1)

    cursor = await db.execute(
        f"""
        SELECT timestamp, fatigue_score, load_score
        FROM predictions
        WHERE user_id = ? AND timestamp >= datetime('now', '-{day_window} day')
        ORDER BY timestamp ASC
        """,
        (user_id,),
    )
    prediction_rows = await cursor.fetchall()

    avg_fatigue = 0.0
    hours_in_high_load = 0.0
    late_night_usage_hours = 0.0
    trend_over_days = 0.0
    if prediction_rows:
        severities = [max(float(row["fatigue_score"]), float(row["load_score"])) for row in prediction_rows]
        avg_fatigue = sum(float(row["fatigue_score"]) for row in prediction_rows) / len(prediction_rows)
        high_count = sum(1 for severity in severities if severity >= 65.0)
        hours_in_high_load = (high_count * 5.0) / 60.0

        late_night_count = 0
        for row in prediction_rows:
            ts = row["timestamp"] or ""
            hour = 0
            if len(ts) >= 13:
                try:
                    hour = int(ts[11:13])
                except Exception:
                    hour = 0
            if hour >= 23 or hour < 5:
                late_night_count += 1
        late_night_usage_hours = (late_night_count * 5.0) / 60.0

        cursor = await db.execute(
            f"""
            SELECT
                substr(timestamp, 1, 10) AS day_key,
                AVG(MAX(fatigue_score, load_score)) AS day_severity
            FROM predictions
            WHERE user_id = ? AND timestamp >= datetime('now', '-{day_window} day')
            GROUP BY day_key
            ORDER BY day_key ASC
            """,
            (user_id,),
        )
        daily_rows = await cursor.fetchall()
        if len(daily_rows) >= 2:
            first = float(daily_rows[0]["day_severity"] or 0.0)
            last = float(daily_rows[-1]["day_severity"] or 0.0)
            trend_over_days = (last - first) / 100.0

    cursor = await db.execute(
        f"""
        SELECT features_json
        FROM feature_windows
        WHERE user_id = ? AND window_end >= datetime('now', '-{day_window} day')
        ORDER BY window_end DESC
        LIMIT 2000
        """,
        (user_id,),
    )
    feature_rows = await cursor.fetchall()
    long_sessions = 0.0
    for row in feature_rows:
        try:
            features = json.loads(row["features_json"])
        except Exception:
            continue
        if float(features.get("current_session_length_min", 0.0)) >= 90.0:
            long_sessions += 1.0

    return {
        "avg_fatigue_score": round(float(avg_fatigue), 4),
        "hours_in_high_load": round(float(hours_in_high_load), 4),
        "long_sessions": round(float(long_sessions), 4),
        "late_night_usage_hours": round(float(late_night_usage_hours), 4),
        "trend_over_days": round(float(trend_over_days), 6),
    }


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
        "eye_fatigue_score": float(row["eye_fatigue_score"] or 0.0),
        "drowsy_flag": bool(row["drowsy_flag"]),
        "final_fatigue_score": float(row["final_fatigue_score"] or row["fatigue_score"] or 0.0),
        "alert_level": row["alert_level"] or "low",
        "alerts": json.loads(row["alerts_json"] or "[]"),
        "missing_inputs": json.loads(row["missing_inputs_json"] or "[]"),
        "instant_fatigue_score": float(row["instant_fatigue_score"] or row["fatigue_score"] or 0.0),
        "instant_load_score": float(row["instant_load_score"] or row["load_score"] or 0.0),
        "smoothed_fatigue_score": float(row["smoothed_fatigue_score"] or row["fatigue_score"] or 0.0),
        "smoothed_load_score": float(row["smoothed_load_score"] or row["load_score"] or 0.0),
        "confidence_level": row["confidence_level"] or "MEDIUM",
        "confidence_components": json.loads(row["confidence_components_json"] or "{}"),
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


async def insert_video_session(
    db: aiosqlite.Connection,
    user_id: str,
    payload: VideoSessionPayload,
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO video_sessions (
            user_id, timestamp, platform, duration_min, source, in_focus_block, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            payload.timestamp.isoformat(),
            payload.platform,
            payload.duration_min,
            payload.source,
            int(payload.in_focus_block),
            payload.note,
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def fetch_video_sessions(db: aiosqlite.Connection, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT *
        FROM video_sessions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def fetch_video_summary(db: aiosqlite.Connection, user_id: str) -> Dict[str, Any]:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    cursor = await db.execute(
        """
        SELECT
            platform,
            COALESCE(SUM(duration_min), 0) AS total_min,
            COUNT(*) AS sessions,
            COALESCE(SUM(CASE WHEN in_focus_block = 1 THEN duration_min ELSE 0 END), 0) AS focus_block_min
        FROM video_sessions
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ?
        GROUP BY platform
        """,
        (user_id, today),
    )
    rows = await cursor.fetchall()
    by_platform = {row["platform"]: float(row["total_min"]) for row in rows}
    daily_total = sum(by_platform.values())
    session_count = int(sum(row["sessions"] for row in rows))
    focus_block_total = float(sum(row["focus_block_min"] for row in rows))

    # Metadata-only proxy score for behavioral disengagement.
    score = min(100.0, daily_total * 1.4 + focus_block_total * 1.1 + max(0, session_count - 2) * 6.0)
    insights: List[str] = []
    if daily_total >= 45:
        insights.append("Short-form usage is elevated today.")
    if focus_block_total >= 20:
        insights.append("A large share happened during focus blocks.")
    if session_count >= 5:
        insights.append("Frequent short sessions can signal context escape.")
    if not insights:
        insights.append("Video usage is currently in a light range.")

    return {
        "daily_total_min": round(daily_total, 2),
        "session_count": session_count,
        "by_platform_min": {key: round(value, 2) for key, value in by_platform.items()},
        "escape_behavior_score": round(score, 2),
        "insights": insights,
    }


async def fetch_recent_telemetry(db: aiosqlite.Connection, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT timestamp, payload_json
        FROM telemetry_minute
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    output: List[Dict[str, Any]] = []
    for row in reversed(rows):
        payload = json.loads(row["payload_json"])
        output.append(
            {
                "timestamp": row["timestamp"],
                "app_name": payload.get("app_name"),
                "active_domain": payload.get("active_domain"),
                "active_seconds": float(payload.get("active_seconds", 0.0)),
                "idle_seconds": float(payload.get("idle_seconds", 0.0)),
                "tab_switches": int(payload.get("tab_switches", 0)),
                "short_video_seconds": float(payload.get("short_video_seconds", 0.0)),
                "key_count": int(payload.get("key_count", 0)),
                "character_count": int(payload.get("character_count", 0)),
            }
        )
    return output


async def insert_eye_observation(
    db: aiosqlite.Connection,
    user_id: str,
    observation: Dict[str, Any],
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO eye_observations (
            user_id, timestamp, source, ear, blink_rate_per_min,
            eye_closure_duration_s, eye_fatigue_score, drowsy_flag, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            observation.get("timestamp") or datetime.now(UTC).isoformat(),
            observation.get("source", "manual"),
            float(observation.get("ear", 0.0)),
            float(observation.get("blink_rate_per_min", 0.0)),
            float(observation.get("eye_closure_duration_s", 0.0)),
            float(observation.get("eye_fatigue_score", 0.0)),
            int(bool(observation.get("drowsy_flag", False))),
            json.dumps(observation.get("warnings", [])),
        ),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def fetch_latest_eye_observation(db: aiosqlite.Connection, user_id: str) -> Optional[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT *
        FROM eye_observations
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
        "timestamp": row["timestamp"],
        "source": row["source"],
        "ear": float(row["ear"] or 0.0),
        "blink_rate_per_min": float(row["blink_rate_per_min"] or 0.0),
        "eye_closure_duration_s": float(row["eye_closure_duration_s"] or 0.0),
        "eye_fatigue_score": float(row["eye_fatigue_score"] or 0.0),
        "drowsy_flag": bool(row["drowsy_flag"]),
        "warnings": json.loads(row["warnings_json"] or "[]"),
    }


async def reset_user_data(db: aiosqlite.Connection, user_id: str) -> None:
    for table in (
        "telemetry_minute",
        "feature_windows",
        "predictions",
        "notifications",
        "self_reports",
        "calibration_labels",
        "chat_events",
        "video_sessions",
        "eye_observations",
        "user_feature_stats",
        "user_profiles",
    ):
        await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    await db.commit()
