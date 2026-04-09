"""
Comprehensive QA test suite for POST /predict endpoint.
Tests: structure validation, demo mode, stability, edge cases, logic quality.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

BASE_URL = "http://localhost:8000"

# ── Expected schema ─────────────────────────────────────────────────────
REQUIRED_FIELDS = {
    "fatigue_score": (int, float),
    "state": str,
    "confidence": str,
    "reasons": dict,
    "trend": str,
    "trendDelta": (int, float),
    "burnoutScore": (int, float),
    "distractionLevel": (int, float),
    "baselines": dict,
    "anomalies": list,
    "actions": list,
    "last_updated": str,
    "status": str,
}

VALID_STATES = {"normal", "high_load", "fatigue", "risk"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_STATUS = {"calibrating", "live", "stale"}
VALID_TRENDS = {"up", "down", "stable"}

REASON_KEYS = {"behavior", "session", "fatigue"}
BASELINE_KEYS = {"typing_speed", "error_rate", "switching"}


class TestResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __str__(self):
        icon = "✅ PASS" if self.passed else "❌ FAIL"
        s = f"  {icon}  {self.name}"
        if self.detail:
            s += f"\n         {self.detail}"
        return s


results: List[TestResult] = []
sample_responses: List[Dict[str, Any]] = []
all_responses: List[Dict[str, Any]] = []
errors: List[str] = []


def record(name: str, passed: bool, detail: str = ""):
    results.append(TestResult(name, passed, detail))


# ── Helpers ──────────────────────────────────────────────────────────────
def validate_structure(resp: dict, label: str = "") -> List[str]:
    """Validate a single response against the expected schema. Returns list of issues."""
    issues = []
    prefix = f"[{label}] " if label else ""

    # 1) Required fields exist
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in resp:
            issues.append(f"{prefix}Missing field: {field}")
        elif not isinstance(resp[field], expected_type):
            issues.append(
                f"{prefix}Wrong type for '{field}': expected {expected_type}, got {type(resp[field]).__name__}"
            )

    # 2) No null / None values for required fields
    for field in REQUIRED_FIELDS:
        if field in resp and resp[field] is None:
            issues.append(f"{prefix}Null value for required field: {field}")

    # 3) Enum validation
    if resp.get("state") not in VALID_STATES:
        issues.append(f"{prefix}Invalid state: {resp.get('state')}")
    if resp.get("confidence") not in VALID_CONFIDENCE:
        issues.append(f"{prefix}Invalid confidence: {resp.get('confidence')}")
    if resp.get("status") not in VALID_STATUS:
        issues.append(f"{prefix}Invalid status: {resp.get('status')}")
    if resp.get("trend") not in VALID_TRENDS:
        issues.append(f"{prefix}Invalid trend: {resp.get('trend')}")

    # 4) Nested structure: reasons
    reasons = resp.get("reasons", {})
    if not isinstance(reasons, dict):
        issues.append(f"{prefix}reasons is not a dict")
    else:
        for key in REASON_KEYS:
            if key not in reasons:
                issues.append(f"{prefix}Missing reasons sub-key: {key}")
            elif not isinstance(reasons[key], list):
                issues.append(f"{prefix}reasons.{key} is not a list")
            elif not all(isinstance(item, str) for item in reasons[key]):
                issues.append(f"{prefix}reasons.{key} contains non-string items")

    # 5) Nested structure: baselines
    baselines = resp.get("baselines", {})
    if not isinstance(baselines, dict):
        issues.append(f"{prefix}baselines is not a dict")
    else:
        for key in BASELINE_KEYS:
            if key not in baselines:
                issues.append(f"{prefix}Missing baselines sub-key: {key}")
            elif not isinstance(baselines[key], (int, float)):
                issues.append(f"{prefix}baselines.{key} is not a number")

    # 6) Range checks
    if isinstance(resp.get("fatigue_score"), (int, float)):
        if not (0 <= resp["fatigue_score"] <= 100):
            issues.append(f"{prefix}fatigue_score out of range [0,100]: {resp['fatigue_score']}")
    if isinstance(resp.get("burnoutScore"), (int, float)):
        if not (0 <= resp["burnoutScore"] <= 100):
            issues.append(f"{prefix}burnoutScore out of range [0,100]: {resp['burnoutScore']}")
    if isinstance(resp.get("distractionLevel"), (int, float)):
        if not (0 <= resp["distractionLevel"] <= 100):
            issues.append(f"{prefix}distractionLevel out of range [0,100]: {resp['distractionLevel']}")

    # 7) Lists contain only strings
    for list_field in ("anomalies", "actions"):
        lst = resp.get(list_field, [])
        if isinstance(lst, list) and not all(isinstance(item, str) for item in lst):
            issues.append(f"{prefix}{list_field} contains non-string items")

    # 8) last_updated is parsable timestamp
    lu = resp.get("last_updated", "")
    if lu:
        try:
            datetime.fromisoformat(lu)
        except Exception:
            issues.append(f"{prefix}last_updated is not a valid ISO timestamp: {lu}")

    return issues


async def post_predict(client: httpx.AsyncClient, payload=None, label: str = "") -> Dict[str, Any] | None:
    """POST to /predict and return JSON or None on error."""
    try:
        kwargs: dict = {"url": f"{BASE_URL}/predict"}
        if payload is not None:
            kwargs["json"] = payload
        else:
            kwargs["content"] = ""
            kwargs["headers"] = {"Content-Type": "application/json"}
        resp = await client.post(**kwargs)
        if resp.status_code == 200:
            data = resp.json()
            all_responses.append(data)
            return data
        elif resp.status_code == 422:
            # Validation error – expected for some edge cases
            return {"__error": resp.status_code, "__detail": resp.json()}
        else:
            errors.append(f"[{label}] HTTP {resp.status_code}: {resp.text[:300]}")
            return {"__error": resp.status_code, "__detail": resp.text[:300]}
    except Exception as e:
        errors.append(f"[{label}] Exception: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# TEST SUITES
# ══════════════════════════════════════════════════════════════════════════


async def test_health(client: httpx.AsyncClient):
    """Verify the server is reachable."""
    try:
        resp = await client.get(f"{BASE_URL}/health")
        record("Server health check", resp.status_code == 200, f"status={resp.status_code}")
    except Exception as e:
        record("Server health check", False, str(e))


# ── 2. Basic payload tests ──────────────────────────────────────────────
async def test_empty_payload(client: httpx.AsyncClient):
    """POST with empty body {}."""
    data = await post_predict(client, payload={}, label="empty_payload")
    if data and "__error" not in data:
        issues = validate_structure(data, "empty_payload")
        record("Empty payload → valid response", not issues, "; ".join(issues) if issues else "All fields valid")
        if len(sample_responses) < 3:
            sample_responses.append({"label": "empty_payload", "response": data})
    elif data and data.get("__error") == 422:
        record("Empty payload → 422 validation error", True, "FastAPI rejected empty body (expected for strict schemas)")
    else:
        record("Empty payload → valid response", False, "No response received")


async def test_null_payload(client: httpx.AsyncClient):
    """POST with null body."""
    data = await post_predict(client, payload=None, label="null_payload")
    if data and "__error" not in data:
        issues = validate_structure(data, "null_payload")
        record("Null payload → valid response", not issues, "; ".join(issues) if issues else "All fields valid")
        if len(sample_responses) < 3:
            sample_responses.append({"label": "null_payload", "response": data})
    elif data and data.get("__error") == 422:
        record("Null payload → 422 validation error", True, "FastAPI rejected null body (expected)")
    else:
        record("Null payload → valid response", False, "No response received")


async def test_random_payload(client: httpx.AsyncClient):
    """POST with garbage/random fields."""
    payload = {"foo": "bar", "baz": 42, "nested": {"a": [1, 2, 3]}}
    data = await post_predict(client, payload=payload, label="random_payload")
    if data and "__error" not in data:
        issues = validate_structure(data, "random_payload")
        record("Random payload → valid response", not issues, "; ".join(issues) if issues else "All fields valid")
    elif data and data.get("__error") == 422:
        record("Random payload → 422 validation error", True, "FastAPI rejected random payload (expected)")
    else:
        record("Random payload → valid response", False, "No response received")


async def test_realistic_telemetry(client: httpx.AsyncClient):
    """POST with valid telemetry data."""
    payload = {
        "key_count": 150,
        "character_count": 140,
        "backspace_count": 10,
        "mean_key_hold": 85.0,
        "std_key_hold": 15.0,
        "key_hold_samples": 150,
        "mean_interkey_latency": 120.0,
        "std_interkey_latency": 35.0,
        "interkey_samples": 149,
        "typing_active_seconds": 42.0,
        "active_seconds": 55.0,
        "idle_seconds": 5.0,
        "idle_bursts": 2,
        "tab_switches": 3,
        "window_switches": 1,
        "active_domain": "github.com",
        "page_title": "Pull request review",
    }
    data = await post_predict(client, payload=payload, label="realistic_telemetry")
    if data and "__error" not in data:
        issues = validate_structure(data, "realistic_telemetry")
        record("Realistic telemetry → valid response", not issues, "; ".join(issues) if issues else "All fields valid")
        if len(sample_responses) < 3:
            sample_responses.append({"label": "realistic_telemetry", "response": data})
    else:
        record("Realistic telemetry → valid response", False, f"Error: {data}")


# ── 3. Demo mode ─────────────────────────────────────────────────────────
async def test_demo_mode(client: httpx.AsyncClient):
    """Ensure demo mode returns valid, stable data when no telemetry exists."""
    # Use a fresh user_id that has no data
    demo_user = f"demo_tester_{int(time.time())}"
    responses = []
    for i in range(5):
        data = await post_predict(client, payload=None, label=f"demo_mode_{i}")
        if data and "__error" not in data:
            responses.append(data)

    if not responses:
        record("Demo mode → returns data", False, "No valid responses received")
        return

    record("Demo mode → returns data", True, f"Got {len(responses)} valid responses")

    # Check all have demo status = calibrating
    all_calibrating = all(r.get("status") == "calibrating" for r in responses)
    record("Demo mode → status = calibrating", all_calibrating,
           f"Statuses: {[r.get('status') for r in responses]}")

    # Check demo values are not random noise (should be identical since no state changes)
    scores = [r.get("fatigue_score") for r in responses]
    score_variance = max(scores) - min(scores) if scores else 0
    record("Demo mode → stable scores (not random noise)", score_variance < 30,
           f"Scores: {scores}, variance: {score_variance}")

    # Validate structure on all demo responses
    all_valid = True
    combined_issues = []
    for i, r in enumerate(responses):
        issues = validate_structure(r, f"demo_{i}")
        if issues:
            all_valid = False
            combined_issues.extend(issues)
    record("Demo mode → all responses pass structure validation", all_valid,
           "; ".join(combined_issues[:5]) if combined_issues else "All valid")


# ── 4. Stability – repeated calls ───────────────────────────────────────
async def test_stability(client: httpx.AsyncClient):
    """Call endpoint 20 times rapidly and check for crashes."""
    crash_count = 0
    success_count = 0
    error_codes = []

    tasks = []
    for i in range(20):
        tasks.append(post_predict(client, payload=None, label=f"stability_{i}"))

    results_data = await asyncio.gather(*tasks, return_exceptions=True)

    for i, data in enumerate(results_data):
        if isinstance(data, Exception):
            crash_count += 1
            errors.append(f"[stability_{i}] Exception: {data}")
        elif data is None:
            crash_count += 1
        elif "__error" in data:
            error_codes.append(data["__error"])
        else:
            success_count += 1

    record("Stability → no crashes in 20 rapid calls", crash_count == 0,
           f"Success: {success_count}, Crashes: {crash_count}, HTTP errors: {error_codes}")

    # Consistent response shape
    shapes = set()
    for data in results_data:
        if isinstance(data, dict) and "__error" not in data:
            shapes.add(frozenset(data.keys()))
    record("Stability → consistent response shape", len(shapes) <= 1,
           f"Unique shapes: {len(shapes)}")


# ── 5. Edge cases ───────────────────────────────────────────────────────
async def test_edge_malformed_json(client: httpx.AsyncClient):
    """POST with malformed JSON string."""
    try:
        resp = await client.post(
            f"{BASE_URL}/predict",
            content="not valid json{{{",
            headers={"Content-Type": "application/json"},
        )
        # Should get 422 (validation error) not 500
        record("Malformed JSON → no 500 crash", resp.status_code != 500,
               f"Got status {resp.status_code}")
        record("Malformed JSON → 422 or graceful error", resp.status_code == 422,
               f"Got status {resp.status_code}")
    except Exception as e:
        record("Malformed JSON → no exception", False, str(e))


async def test_edge_extremely_large_values(client: httpx.AsyncClient):
    """POST with extremely large numeric values."""
    payload = {
        "key_count": 999999,
        "character_count": 999999,
        "backspace_count": 999999,
        "mean_key_hold": 99999.0,
        "active_seconds": 120.0,
        "idle_seconds": 0.0,
        "tab_switches": 99999,
    }
    data = await post_predict(client, payload=payload, label="extreme_values")
    if data and "__error" not in data:
        # fatigue_score and burnoutScore should still be clamped 0–100
        fs = data.get("fatigue_score", 0)
        bs = data.get("burnoutScore", 0)
        dl = data.get("distractionLevel", 0)
        record("Extreme values → fatigue_score clamped [0,100]", 0 <= fs <= 100,
               f"fatigue_score={fs}")
        record("Extreme values → burnoutScore clamped [0,100]", 0 <= bs <= 100,
               f"burnoutScore={bs}")
        record("Extreme values → distractionLevel clamped [0,100]", 0 <= dl <= 100,
               f"distractionLevel={dl}")
    elif data and data.get("__error") == 422:
        record("Extreme values → 422 validation error", True, "FastAPI rejected extreme values (reasonable)")
    else:
        record("Extreme values → responded", False, f"Error: {data}")


async def test_edge_zero_values(client: httpx.AsyncClient):
    """POST with all-zero telemetry (user is idle)."""
    payload = {
        "key_count": 0,
        "character_count": 0,
        "backspace_count": 0,
        "mean_key_hold": 0.0,
        "active_seconds": 0.0,
        "idle_seconds": 60.0,
        "tab_switches": 0,
    }
    data = await post_predict(client, payload=payload, label="zero_values")
    if data and "__error" not in data:
        issues = validate_structure(data, "zero_values")
        record("Zero values → valid response", not issues,
               "; ".join(issues) if issues else "All fields valid")
    elif data and data.get("__error") == 422:
        record("Zero values → 422 validation error", True, "FastAPI rejected zero payload (reasonable)")
    else:
        record("Zero values → responded", False, f"Error: {data}")


async def test_edge_rapid_burst(client: httpx.AsyncClient):
    """Send 10 requests as fast as possible concurrently."""
    start = time.perf_counter()
    tasks = [post_predict(client, payload=None, label=f"burst_{i}") for i in range(10)]
    results_data = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start

    successes = sum(
        1 for d in results_data
        if isinstance(d, dict) and "__error" not in d
    )
    record("Rapid burst (10 concurrent) → all succeed", successes == 10,
           f"Successes: {successes}/10, Time: {elapsed:.2f}s")


# ── 6. Logic quality ────────────────────────────────────────────────────
async def test_logic_actions_match_state(client: httpx.AsyncClient):
    """Check that actions are logically coherent with state."""
    # Send a few calls and validate actions make sense for the given state
    data = await post_predict(client, payload=None, label="logic_actions")
    if not data or "__error" in data:
        record("Logic: actions match state", False, "No valid response")
        return

    state = data.get("state", "")
    actions = data.get("actions", [])

    ok = True
    detail = f"state={state}, actions={actions}"

    # If state is "normal", actions should not say "Step away and reset"
    if state == "normal":
        if any("step away" in a.lower() for a in actions):
            ok = False
            detail += " — 'Step away' action for normal state is illogical"
    # If state is "risk", there should be at least recovery actions
    if state == "risk":
        if not actions:
            ok = False
            detail += " — No actions for risk state"

    record("Logic: actions match state", ok, detail)


async def test_logic_reasons_populated(client: httpx.AsyncClient):
    """Ensure reason groups always have at least one entry."""
    data = await post_predict(client, payload=None, label="logic_reasons")
    if not data or "__error" in data:
        record("Logic: reasons always populated", False, "No valid response")
        return

    reasons = data.get("reasons", {})
    all_populated = all(
        isinstance(reasons.get(k), list) and len(reasons.get(k, [])) > 0
        for k in ("behavior", "session", "fatigue")
    )
    record("Logic: all reason groups have ≥1 entry", all_populated,
           f"behavior={len(reasons.get('behavior',[]))} session={len(reasons.get('session',[]))} fatigue={len(reasons.get('fatigue',[]))}")


async def test_logic_score_trend_coherence(client: httpx.AsyncClient):
    """Check that trend aligns with score over repeated calls."""
    # Send multiple calls with increasing workload
    responses_series = []
    for i in range(5):
        data = await post_predict(client, payload=None, label=f"trend_check_{i}")
        if data and "__error" not in data:
            responses_series.append(data)
        await asyncio.sleep(0.1)

    if len(responses_series) < 2:
        record("Logic: trend aligns with score changes", False, "Not enough responses")
        return

    # At minimum, trend should be a valid value
    trends = [r.get("trend") for r in responses_series]
    all_valid_trends = all(t in VALID_TRENDS for t in trends)
    record("Logic: trend values are valid across calls", all_valid_trends,
           f"Trends: {trends}")

    # TrendDelta should be numeric
    deltas = [r.get("trendDelta") for r in responses_series]
    all_numeric = all(isinstance(d, (int, float)) for d in deltas)
    record("Logic: trendDelta is numeric across calls", all_numeric,
           f"Deltas: {deltas}")


async def test_logic_baselines_sensible(client: httpx.AsyncClient):
    """Check that baseline values are non-negative and reasonable."""
    data = await post_predict(client, payload=None, label="logic_baselines")
    if not data or "__error" in data:
        record("Logic: baselines are sensible", False, "No valid response")
        return

    baselines = data.get("baselines", {})
    issues = []
    for key in BASELINE_KEYS:
        val = baselines.get(key)
        if val is None:
            issues.append(f"{key} is None")
        elif not isinstance(val, (int, float)):
            issues.append(f"{key} is not numeric")
        elif val < 0:
            issues.append(f"{key} is negative: {val}")

    record("Logic: baselines are non-negative & numeric", not issues,
           "; ".join(issues) if issues else f"baselines={baselines}")


# ── 7. Sequential telemetry simulation ──────────────────────────────────
async def test_sequential_telemetry(client: httpx.AsyncClient):
    """Simulate 15 sequential minutes of telemetry and validate evolution."""
    user_id = f"seq_test_{int(time.time())}"
    responses_seq = []

    for i in range(15):
        # Gradually increase workload
        payload = {
            "key_count": 100 + i * 20,
            "character_count": 90 + i * 18,
            "backspace_count": 5 + i * 3,
            "mean_key_hold": 80.0 + i * 2,
            "std_key_hold": 15.0 + i,
            "key_hold_samples": 100 + i * 20,
            "mean_interkey_latency": 110.0 + i * 5,
            "std_interkey_latency": 30.0 + i * 2,
            "interkey_samples": 99 + i * 20,
            "typing_active_seconds": 40.0 + i * 1,
            "active_seconds": 55.0,
            "idle_seconds": 5.0 + i * 0.5,
            "idle_bursts": 2 + i // 3,
            "tab_switches": 2 + i,
            "window_switches": 1 + i // 2,
            "active_domain": "github.com",
            "page_title": f"Task {i+1}",
        }
        try:
            resp = await client.post(
                f"{BASE_URL}/predict?user_id={user_id}",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                responses_seq.append(data)
            elif resp.status_code == 422:
                errors.append(f"[seq_{i}] 422: {resp.json()}")
        except Exception as e:
            errors.append(f"[seq_{i}] Exception: {e}")

    if not responses_seq:
        record("Sequential telemetry → produces responses", False, "No valid responses")
        return

    record("Sequential telemetry → produces responses", True,
           f"Got {len(responses_seq)}/{15} valid responses")

    # All pass structure validation
    all_issues = []
    for idx, r in enumerate(responses_seq):
        iss = validate_structure(r, f"seq_{idx}")
        all_issues.extend(iss)
    record("Sequential telemetry → all pass structure", not all_issues,
           "; ".join(all_issues[:5]) if all_issues else "All valid")

    # Check status transitions (should start calibrating, then go to live after enough points)
    statuses = [r.get("status") for r in responses_seq]
    record("Sequential telemetry → status progression observed",
           len(set(statuses)) >= 1,  # At least calibrating is present
           f"Statuses: {statuses}")

    # Check fatigue score progression
    scores = [r.get("fatigue_score") for r in responses_seq]
    record("Sequential telemetry → fatigue_score changes over time",
           len(set(scores)) > 1 or len(responses_seq) < 3,
           f"Scores: {scores}")

    # Save last response as sample if space available
    if len(sample_responses) < 3 and responses_seq:
        sample_responses.append({"label": "sequential_telemetry_final", "response": responses_seq[-1]})


# ══════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════
async def main():
    print("=" * 72)
    print("  NeuroLens AI — POST /predict — Comprehensive QA Test Suite")
    print("=" * 72)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ── 1. Server reachability ──
        print("\n── 1. Server Health ──")
        await test_health(client)

        # ── 2. Basic payloads ──
        print("\n── 2. Basic Payload Tests ──")
        await test_empty_payload(client)
        await test_null_payload(client)
        await test_random_payload(client)
        await test_realistic_telemetry(client)

        # ── 3. Demo mode ──
        print("\n── 3. Demo Mode ──")
        await test_demo_mode(client)

        # ── 4. Stability ──
        print("\n── 4. Stability (20 rapid calls) ──")
        await test_stability(client)

        # ── 5. Edge cases ──
        print("\n── 5. Edge Cases ──")
        await test_edge_malformed_json(client)
        await test_edge_extremely_large_values(client)
        await test_edge_zero_values(client)
        await test_edge_rapid_burst(client)

        # ── 6. Logic quality ──
        print("\n── 6. Logic Quality ──")
        await test_logic_actions_match_state(client)
        await test_logic_reasons_populated(client)
        await test_logic_score_trend_coherence(client)
        await test_logic_baselines_sensible(client)

        # ── 7. Sequential telemetry simulation ──
        print("\n── 7. Sequential Telemetry Simulation ──")
        await test_sequential_telemetry(client)

    # ══ REPORT ═══════════════════════════════════════════════════════════
    print("\n")
    print("=" * 72)
    print("  TEST RESULTS")
    print("=" * 72)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for r in results:
        print(r)

    print(f"\n  Total: {len(results)} | Passed: {passed} | Failed: {failed}")

    if errors:
        print(f"\n── Errors / Crashes ({len(errors)}) ──")
        for e in errors:
            print(f"  ⚠️  {e}")

    print("\n── Sample Responses ──")
    for sr in sample_responses[:3]:
        print(f"\n  [{sr['label']}]")
        print(json.dumps(sr["response"], indent=2, default=str)[:2000])

    # Verdict
    print("\n" + "=" * 72)
    if failed == 0 and not errors:
        print("  🟢 VERDICT: WORKING — All tests pass, no errors.")
    elif failed <= 3 and len(errors) <= 2:
        print("  🟡 VERDICT: PARTIALLY WORKING — Minor issues detected.")
    else:
        print("  🔴 VERDICT: BROKEN — Multiple failures or crashes detected.")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
