/**
 * NeuroLens AI — API Client
 *
 * Handles communication with the FastAPI backend.
 * Uses VITE_API_BASE_URL from env or defaults to localhost.
 */

/// <reference types="vite/client" />

const BASE_URL: string =
  (import.meta.env?.VITE_API_BASE_URL as string) || 'http://127.0.0.1:8001'


const TIMEOUT_MS = 3000

/* ── Telemetry input shape (subset of MinuteTelemetryPayload) ── */

export interface TelemetryInput {
  key_count?: number
  character_count?: number
  backspace_count?: number
  mean_interkey_latency?: number
  std_interkey_latency?: number
  interkey_samples?: number
  mean_key_hold?: number
  std_key_hold?: number
  key_hold_samples?: number
  tab_switches?: number
  window_switches?: number
  window_duration_s?: number
  active_seconds?: number
  idle_seconds?: number
  idle_bursts?: number
  typing_active_seconds?: number
  app_name?: string
  active_domain?: string
  short_video_seconds?: number
  short_video_sessions?: number
  timestamp?: string
}

/* ── Simulated telemetry generator ── */

const DEMO_DOMAINS = [
  'github.com',
  'docs.google.com',
  'notion.so',
  'stackoverflow.com',
  'figma.com',
  'code.visualstudio.com',
]

/**
 * Generates realistic-looking telemetry that exercises the full
 * backend ML pipeline (XGBoost + feature extraction + fusion).
 */
export function generateSimulatedTelemetry(): TelemetryInput {
  const keyCount = Math.round(80 + Math.random() * 120) // 80–200 keys/min
  const backspaceCount = Math.round(
    keyCount * (0.02 + Math.random() * 0.06),
  ) // 2–8 % error rate
  const charCount = Math.max(0, keyCount - backspaceCount)
  const activeSeconds = Math.round(42 + Math.random() * 18) // 42–60 s
  const idleSeconds = 60 - activeSeconds

  return {
    key_count: keyCount,
    character_count: charCount,
    backspace_count: backspaceCount,
    mean_interkey_latency: Math.round(95 + Math.random() * 85), // 95–180 ms
    std_interkey_latency: Math.round(12 + Math.random() * 28),
    interkey_samples: keyCount,
    mean_key_hold: Math.round(68 + Math.random() * 35), // 68–103 ms
    std_key_hold: Math.round(6 + Math.random() * 14),
    key_hold_samples: keyCount,
    tab_switches: Math.round(Math.random() * 5), // 0–5 per window
    window_switches: Math.round(Math.random() * 3),
    window_duration_s: 60,
    active_seconds: activeSeconds,
    idle_seconds: idleSeconds,
    idle_bursts: Math.round(Math.random() * 3),
    typing_active_seconds: Math.round(activeSeconds * (0.6 + Math.random() * 0.2)),
    app_name: 'browser',
    active_domain:
      DEMO_DOMAINS[Math.floor(Math.random() * DEMO_DOMAINS.length)],
    short_video_seconds: 0,
    short_video_sessions: 0,
    timestamp: new Date().toISOString(),
  }
}

/* ── Main fetch function ── */

/**
 * POST /predict with optional telemetry payload.
 * Throws on network/timeout/HTTP errors — caller handles fallback.
 */
export async function fetchPrediction(
  input?: TelemetryInput,
  userId = 'default',
): Promise<Record<string, unknown>> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(
      `${BASE_URL}/predict?user_id=${encodeURIComponent(userId)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input ?? {}),
        signal: controller.signal,
      },
    )

    if (!res.ok) {
      throw new Error(`API ${res.status}: ${res.statusText}`)
    }

    return (await res.json()) as Record<string, unknown>
  } finally {
    clearTimeout(timeout)
  }
}
