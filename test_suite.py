import asyncio
import httpx
import websockets
import json

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/live"

async def test_1_api_works():
    print("🧪 Test 1 — API works (Normal State)")
    async with httpx.AsyncClient() as client:
        # We need to hit /metrics
        payload = {
            "typing_speed": 200,
            "error_rate": 0.1,
            "avg_latency": 120,
            "tab_switches": 2,
            "idle_time_ms": 1000,
            "key_count": 50,
            "backspace_count": 5,
            "session_duration_s": 300,
            "active_time_ratio": 0.8,
            "fatigue_score": 0,
            "fatigue_level": "INACTIVE"
        }
        res = await client.post(f"{BASE_URL}/metrics?session_id=test_session", json=payload)
        data = res.json()
        assert res.status_code == 200
        score_res = data["score_result"]
        print(f"✅ Received score: {score_res['score']}, level: {score_res['level']}")
        if score_res.get("coach"):
            print("✅ Default coach present")
        if not score_res.get("llm_coach"):
            print("✅ llm_coach is null (This is expected for NORMAL)")
        print("—" * 40)

async def test_2_high_fatigue():
    print("🧪 Test 2 — HIGH FATIGUE")
    async with httpx.AsyncClient() as client:
        # Hit 5 times to trigger burnout / trend, or just once for score > 70
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
            "fatigue_level": "INACTIVE"
        }
        res = await client.post(f"{BASE_URL}/metrics?session_id=test_session", json=payload)
        data = res.json()
        score_res = data["score_result"]
        print(f"✅ Received score: {score_res['score']} (Expected > 70)")
        print(f"✅ Level: {score_res['level']} (Expected HIGH)")
        if score_res.get("recovery_action"):
            print("✅ Recovery action present")
        if score_res.get("reasons"):
            print(f"✅ Reasons present: {score_res['reasons']}")
        print("—" * 40)


async def test_4_websocket_live_stream():
    print("🧪 Test 4 — Websocket Live Stream & Test 9 — REAL FLOW")
    
    async with websockets.connect(WS_URL) as ws:
        # Trigger an update via HTTP
        async with httpx.AsyncClient() as client:
            payload = {
                "typing_speed": 100,
                "error_rate": 0.35,
                "avg_latency": 350,
                "tab_switches": 12,
                "idle_time_ms": 0,
                "key_count": 60,
                "backspace_count": 21,
                "session_duration_s": 1200,
                "active_time_ratio": 0.95,
                "fatigue_score": 0,
                "fatigue_level": "INACTIVE"
            }
            res = await client.post(f"{BASE_URL}/metrics?session_id=test_ws", json=payload)

        # Wait for INSTANT WS payload
        try:
            msg1 = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data1 = json.loads(msg1)
            print(f"✅ WS 1 (Instant): type={data1.get('type')}, llm_coach={data1.get('llm_coach')}")
            
            # Wait for LLM update payload
            msg2 = await asyncio.wait_for(ws.recv(), timeout=8.0)
            data2 = json.loads(msg2)
            print(f"✅ WS 2 (Delayed LLM): type={data2.get('type')}, llm_coach={data2.get('llm_coach')}")
            if data2.get('llm_coach'):
                print("💥 CRITICAL DEMO MOMENT PASSED - LLM Update Received over WebSockets!")
            
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for WS update")
        print("—" * 40)


async def main():
    await test_1_api_works()
    await test_2_high_fatigue()
    await test_4_websocket_live_stream()
    
    print("\n✅ API and Data flow tests complete")

if __name__ == "__main__":
    asyncio.run(main())
