"""
NeuroLens AI -- LLM Coach Service

Uses OpenRouter (free tier) with microsoft/phi-4-mini-instruct
to generate intelligent, context-aware coaching messages from
scored behavioral data.

Why OpenRouter over Anthropic / HuggingFace:
  - Free tier: phi-4-mini-instruct & llama-3.1-8b are 100% free
  - OpenAI-compatible API (httpx, no new SDK)
  - No model downloads, no GPU, no RAM overhead
  - Swap models with a single constant change

Design principles (unchanged from previous):
  - Only called for HIGH/ELEVATED/DEEP_FOCUS states
  - 5-minute cache per session to avoid hammering the API
  - Full graceful fallback to rule-based coach if LLM unavailable
  - Strict 1-2 sentence output, no markdown, no preamble
  - Institution-mode-aware tone (developer / student / organization)

Architecture:
  Extension -> Backend scorer -> LLM enrichment (async) -> Dashboard
  Dashboard gets rule-based coach instantly,
  LLM-refined coach arrives via WebSocket within ~1s.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── OpenRouter config ──────────────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Best FREE model on OpenRouter for structured instruction-following:
#   microsoft/phi-4-mini-instruct  — elite reasoning, ~0.3s latency, free
# Premium alternatives (use if you have credits):
#   meta-llama/llama-3.1-8b-instruct:free
#   mistralai/mistral-7b-instruct:free
#   qwen/qwen-2.5-7b-instruct:free
PRIMARY_MODEL   = "microsoft/phi-4-mini-instruct"
FALLBACK_MODEL  = "meta-llama/llama-3.1-8b-instruct:free"

# Request config
REQUEST_TIMEOUT_S = 8       # WebSocket latency budget
MAX_TOKENS_COACH  = 120
MAX_TOKENS_SUMMARY = 220
TEMPERATURE_COACH  = 0.35   # Low: consistent, precise
TEMPERATURE_SUMMARY = 0.30

# Cache
_cache: dict[str, dict] = {}
CACHE_TTL_S = 300  # 5 minutes

# Lazy shared httpx client
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> Optional[httpx.AsyncClient]:
    global _http_client
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set -- LLM coaching disabled. "
                       "Get a free key at https://openrouter.ai/keys")
        return None
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url="https://openrouter.ai",
            headers={
                "Authorization":  f"Bearer {api_key}",
                "HTTP-Referer":   "https://neurolens.ai",   # identifies your app in OR dashboard
                "X-Title":        "NeuroLens AI",
                "Content-Type":   "application/json",
            },
            timeout=REQUEST_TIMEOUT_S,
        )
    return _http_client


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_key(session_id: str, level: str) -> str:
    return f"{session_id}:{level}"


def _get_cached(session_id: str, level: str) -> Optional[str]:
    entry = _cache.get(_cache_key(session_id, level))
    if entry and time.time() < entry["expires_at"]:
        return entry["message"]
    return None


def _set_cache(session_id: str, level: str, message: str):
    _cache[_cache_key(session_id, level)] = {
        "message":    message,
        "expires_at": time.time() + CACHE_TTL_S,
    }


# ── Prompt engineering ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are NeuroLens AI -- a precise cognitive performance coach embedded in a real-time brain monitoring system.

You receive live behavioral data from a user's keyboard patterns and tell them exactly what's happening and what to do.

Rules:
- Maximum 2 sentences. Never more.
- Be specific -- use the numbers you are given.
- Lead with the key signal, end with a clear action.
- Tone: calm, data-driven, supportive. Not dramatic.
- No markdown, no bullet points, no preamble like "Based on your data..."
- Never start with "I" or "Your data shows".

Examples of good output:
"Error rate is 3x your baseline and latency has jumped 40ms -- your prefrontal cortex is struggling. Take 3 minutes away from the screen now."
"You've been in deep focus for 8 minutes with near-zero errors -- this is peak cognitive performance, protect this window."
"Typing speed dropped 28% in the last window while tab switches doubled -- you're mentally overloaded. Finish this thought, then step away."
"""


def _build_coach_prompt(data: dict) -> str:
    mode = data.get("institution_mode", "student")
    mode_context = {
        "student":      "The user is a student working on coursework or studying.",
        "developer":    "The user is a software developer writing or reviewing code.",
        "organization": "The user is a knowledge worker in an enterprise environment.",
    }.get(mode, "The user is a knowledge worker.")

    # Build structured signal injection from reason factors
    signals_text = ""
    structured = data.get("structured_reasons", [])
    if structured:
        lines = []
        for r in structured[:3]:
            factor = r.get("factor", "unknown") if isinstance(r, dict) else getattr(r, "factor", "unknown")
            impact = r.get("impact", "+0") if isinstance(r, dict) else getattr(r, "impact", "+0")
            desc = r.get("description", "") if isinstance(r, dict) else getattr(r, "description", "")
            lines.append(f"  - {factor.upper()} ({impact} impact): {desc}")
        signals_text = "\n\nUser is experiencing:\n" + "\n".join(lines)

    # Contribution breakdown
    contribution_text = ""
    contrib = data.get("contribution")
    if contrib and isinstance(contrib, dict):
        parts = [f"{k}: {v.get('pct', 0)}%" for k, v in contrib.items() if isinstance(v, dict)]
        if parts:
            contribution_text = f"\nScore contribution: {', '.join(parts)}"

    baseline_text = ""
    if data.get("baseline_used"):
        baseline_text = "\n(Scores are relative to this user's personal baseline, not population averages.)"

    trend_text = ""
    if data.get("trend_direction") and data["trend_direction"] != "STABLE":
        velocity = data.get("trend_velocity", 0)
        vel_str = f" (velocity {velocity:+.1f}/window)" if velocity else ""
        trend_text = f"\nTrend: load is {data['trend_direction'].lower()}{vel_str} over the last 5 minutes."

    burnout_text = ""
    if data.get("burnout_risk"):
        trajectory = data.get("burnout_trajectory", "stable")
        burnout_text = f"\nWARNING: Burnout risk detected — trajectory: {trajectory}."

    focus_text = ""
    if data.get("cognitive_state") == "DEEP_FOCUS":
        focus_text = f"\nUser has been in deep focus for {data.get('focus_streak_mins', 0)} minutes."

    return f"""{mode_context}

Current cognitive state: {data.get('cognitive_state', 'UNKNOWN')}
Fatigue score: {data.get('score', 0)}/100 (Brain performance: {data.get('performance_score', 0)}%)
Typing speed: {data.get('typing_speed', 0)} cpm
Error rate: {round(data.get('error_rate', 0) * 100, 1)}%
Keystroke latency: {data.get('avg_latency', 0)}ms
Tab switches (last 30s): {data.get('tab_switches', 0)}
Session duration: {round(data.get('session_duration_s', 0) / 60, 1)} minutes
Active time ratio: {round(data.get('active_time_ratio', 0) * 100)}%{signals_text}{contribution_text}{baseline_text}{trend_text}{burnout_text}{focus_text}

Give:
1. One short actionable suggestion tied to the top contributing factor
2. One behavior correction for the second factor"""


# ── Core OpenRouter call ───────────────────────────────────────────────────────

async def _call_openrouter(
    system: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    model: str = PRIMARY_MODEL,
) -> Optional[str]:
    """
    Makes a single async call to OpenRouter's chat completions endpoint.
    Returns the assistant message text, or None on failure.
    Automatically retries once with FALLBACK_MODEL if PRIMARY_MODEL fails.
    """
    client = _get_http_client()
    if client is None:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system",  "content": system},
            {"role": "user",    "content": user_prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }

    try:
        response = await client.post("/api/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (429, 503) and model != FALLBACK_MODEL:
            logger.warning(f"OpenRouter primary model failed ({e.response.status_code}), retrying with fallback...")
            return await _call_openrouter(system, user_prompt, max_tokens, temperature, FALLBACK_MODEL)
        logger.warning(f"OpenRouter HTTP error: {e.response.status_code} -- {e.response.text[:200]}")
        return None

    except (httpx.TimeoutException, httpx.RequestError) as e:
        if model != FALLBACK_MODEL:
            logger.warning(f"OpenRouter timeout/network error, retrying with fallback: {e}")
            return await _call_openrouter(system, user_prompt, max_tokens, temperature, FALLBACK_MODEL)
        logger.warning(f"OpenRouter fallback also failed: {e}")
        return None

    except (KeyError, IndexError, ValueError) as e:
        logger.warning(f"OpenRouter unexpected response shape: {e}")
        return None


# ── Public interface ───────────────────────────────────────────────────────────

async def generate_coach_message(
    data: dict,
    session_id: str = "default",
) -> Optional[str]:
    """
    Generate an LLM coaching message for the given scored metrics.

    Only fires for HIGH / ELEVATED / DEEP_FOCUS states.
    Returns None if LLM is unavailable (caller uses rule-based coach as fallback).

    data keys: score, performance_score, level, cognitive_state,
               typing_speed, error_rate, avg_latency, tab_switches,
               session_duration_s, active_time_ratio, reasons, baseline_used,
               trend_direction, burnout_risk, focus_streak_mins, institution_mode
    """
    level = data.get("level", "NORMAL")

    # Only enrich actionable states -- NORMAL/INACTIVE gets rule-based coach
    if level in ("NORMAL", "INACTIVE"):
        return None

    # Cache hit
    cached = _get_cached(session_id, level)
    if cached:
        logger.debug(f"LLM cache hit: session={session_id} level={level}")
        return cached

    prompt = _build_coach_prompt(data)
    message = await _call_openrouter(
        system=SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=MAX_TOKENS_COACH,
        temperature=TEMPERATURE_COACH,
    )

    if message:
        # Truncate if model overruns (phi-4-mini is well-behaved but safe-guard anyway)
        if len(message) > 320:
            message = message[:320].rsplit(".", 1)[0] + "."
        _set_cache(session_id, level, message)
        logger.info(f"LLM coach [phi-4-mini]: session={session_id} level={level} | {message[:70]}...")

    return message


async def generate_session_summary(
    stats: dict,
    session_id: str = "default",
) -> Optional[str]:
    """
    Generate a session-end performance summary via LLM.
    Called from GET /metrics/session-summary.

    stats keys: duration_mins, avg_score, peak_score, deep_focus_pct,
                high_load_pct, burnout_risk, institution_mode
    """
    mode = stats.get("institution_mode", "student")
    mode_context = {
        "student":      "university student",
        "developer":    "software developer",
        "organization": "knowledge worker",
    }.get(mode, "knowledge worker")

    prompt = f"""Generate a 3-sentence cognitive performance report for a {mode_context}.

Session data:
- Duration: {stats.get('duration_mins', 0):.1f} minutes
- Average fatigue score: {stats.get('avg_score', 0):.1f}/100
- Peak fatigue: {stats.get('peak_score', 0):.1f}/100
- Time in deep focus: {stats.get('deep_focus_pct', 0):.1f}%
- Time in high load: {stats.get('high_load_pct', 0):.1f}%
- Burnout risk triggered: {stats.get('burnout_risk', False)}

Rules:
- Sentence 1: What happened (use the specific numbers).
- Sentence 2: The key insight or cognitive pattern.
- Sentence 3: One concrete, actionable recommendation for the next session.
- No markdown, no preamble, no bullet points."""

    system = "You are a cognitive performance analyst. Be precise, data-driven, and concise."

    summary = await _call_openrouter(
        system=system,
        user_prompt=prompt,
        max_tokens=MAX_TOKENS_SUMMARY,
        temperature=TEMPERATURE_SUMMARY,
    )

    if summary:
        logger.info(f"Session summary generated for session={session_id}")

    return summary
