import unittest
import uuid
import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from cognitive_engine import ENGINE
from database import init_db
from main import app
from schema import MinuteTelemetryPayload, OnboardingProfile


class RealtimePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.run(init_db())
        cls.client = TestClient(app)

    def test_feature_builder_produces_required_fields(self):
        user_id = f"unit-{uuid.uuid4()}"
        profile = OnboardingProfile()
        base = datetime.utcnow()
        windows = [
            MinuteTelemetryPayload(
                timestamp=base + timedelta(minutes=index),
                key_count=100 + index * 10,
                character_count=85 + index * 10,
                backspace_count=8 + index,
                mean_key_hold=85,
                std_key_hold=12,
                key_hold_samples=40,
                mean_interkey_latency=140 + index * 5,
                std_interkey_latency=20,
                interkey_samples=50,
                typing_active_seconds=25,
                active_seconds=40,
                idle_seconds=20,
                idle_bursts=1,
                tab_switches=2 + index,
                window_switches=2 + index,
                active_domain="docs.example.com",
            )
            for index in range(5)
        ]
        for window in windows:
            ENGINE.append_window(user_id, window)

        features = ENGINE.build_feature_vector(user_id, profile, windows, [])
        for name in [
            "mean_key_hold",
            "std_interkey_latency",
            "typing_speed_cpm",
            "error_rate",
            "fragmentation_index",
            "time_of_day_sin",
            "z_typing_speed_cpm",
            "rolling_mean_typing_speed_cpm",
        ]:
            self.assertIn(name, features)

    def test_ml_status_endpoint(self):
        response = self.client.get("/ml/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertGreater(payload["feature_count"], 10)

    def test_ingest_returns_live_state_and_history(self):
        user_id = f"api-{uuid.uuid4()}"
        profile_response = self.client.post(
            f"/profile/onboarding?user_id={user_id}",
            json=OnboardingProfile().model_dump(),
        )
        self.assertEqual(profile_response.status_code, 200)

        base = datetime.utcnow()
        for minute in range(6):
            payload = MinuteTelemetryPayload(
                timestamp=base + timedelta(minutes=minute),
                key_count=120,
                character_count=96,
                backspace_count=10 + minute,
                mean_key_hold=92,
                std_key_hold=14,
                key_hold_samples=60,
                mean_interkey_latency=150 + minute * 8,
                std_interkey_latency=28,
                interkey_samples=70,
                typing_active_seconds=28,
                active_seconds=40,
                idle_seconds=18,
                idle_bursts=1,
                tab_switches=3 + minute,
                window_switches=3 + minute,
                active_domain="mail.google.com" if minute % 2 else "docs.google.com",
            ).model_dump(mode="json")
            response = self.client.post(f"/metrics?user_id={user_id}", json=payload)
            self.assertEqual(response.status_code, 200)

        latest = self.client.get(f"/state/latest?user_id={user_id}")
        self.assertEqual(latest.status_code, 200)
        state = latest.json()
        self.assertIn("fatigue_score", state)
        self.assertIn("load_score", state)
        self.assertIn("state_label", state)

        history = self.client.get(f"/metrics/history?user_id={user_id}&limit=20")
        self.assertEqual(history.status_code, 200)
        self.assertGreaterEqual(len(history.json()["points"]), 6)


if __name__ == "__main__":
    unittest.main()
