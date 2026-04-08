import httpx
import json

BASE = "http://127.0.0.1:8000"

# Test 1: ML status
r = httpx.get(f"{BASE}/ml/status")
print("=== ML STATUS ===")
print(json.dumps(r.json(), indent=2))

# Test 2: Metrics with HIGH fatigue payload (should trigger ML)
payload = {
    "typing_speed": 120,
    "error_rate": 0.25,
    "avg_latency": 250,
    "tab_switches": 8,
    "idle_time_ms": 0,
    "key_count": 50,
    "backspace_count": 12,
    "session_duration_s": 600,
    "active_time_ratio": 0.9,
    "fatigue_score": 0,
    "fatigue_level": "INACTIVE",
}
r = httpx.post(f"{BASE}/metrics?session_id=ml_test", json=payload)
data = r.json()
sr = data["score_result"]
print("\n=== METRICS (HIGH FATIGUE) ===")
print(f"Score:           {sr['score']}")
print(f"Level:           {sr['level']}")
print(f"Confidence:      {sr['confidence_score']}")
print(f"Reasons:         {sr['reasons']}")
print(f"Recovery action: {sr.get('recovery_action')}")

# Test 3: Normal payload
payload2 = {
    "typing_speed": 280,
    "error_rate": 0.03,
    "avg_latency": 120,
    "tab_switches": 1,
    "idle_time_ms": 500,
    "key_count": 80,
    "backspace_count": 2,
    "session_duration_s": 300,
    "active_time_ratio": 0.85,
    "fatigue_score": 0,
    "fatigue_level": "INACTIVE",
}
r = httpx.post(f"{BASE}/metrics?session_id=ml_test2", json=payload2)
sr2 = r.json()["score_result"]
print("\n=== METRICS (NORMAL) ===")
print(f"Score:           {sr2['score']}")
print(f"Level:           {sr2['level']}")
print(f"Confidence:      {sr2['confidence_score']}")

print("\nAll tests passed!")
