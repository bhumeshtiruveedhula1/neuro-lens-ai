"""
NeuroLens AI -- Scoring Service

Server-side cognitive load engine. Adds to the extension's local scorer:
  1. Persistent baseline comparison (personalised AI)
  2. Rolling trend detection across the last N windows
  3. Burnout risk prediction (sustained high load)
  4. Deep focus detection + streak tracking
  5. Session fatigue amplifier
  6. Recovery action engine
  7. Explainability reasons list
  8. Performance score (100 - fatigue)

Research basis:
  - Keystroke dynamics AUC 72-87% (Tseng et al., 2021; IJCRT 2025)
  - EMA for adaptive baselines (standard signal processing)
  - Micro-break meta-analysis (Albulescu et al., 2022)
"""

from __future__ import annotations
from typing import Optional
from backend.core.schema import (
    MetricsPayload, ScoreResult, RecoveryAction, ReasonFactor,
    FatigueLevel, CognitiveState, TrendAnalysis
)


# Config
FATIGUE_HIGH       = 70
FATIGUE_ELEVATED   = 50
BURNOUT_WINDOW     = 5     # consecutive HIGH windows -> burnout risk
TREND_WINDOW       = 10    # rolling window for trend score
BASELINE_ALPHA     = 0.15  # EMA smoothing
MIN_BASELINE_SAMP  = 5     # samples before baseline is trusted


# Normalisation helpers

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _norm(value: float, low: float, high: float, invert: bool = False) -> float:
    """Map value linearly into [0, 1]. invert=True: higher value -> higher output."""
    span = high - low
    if span == 0:
        return 0.0
    ratio = _clamp((value - low) / span, 0.0, 1.0)
    return ratio if invert else 1.0 - ratio


# Scoring weights (4-factor model)
W_TYPING  = 0.30
W_ERROR   = 0.20
W_LATENCY = 0.30
W_TABS    = 0.20


# Main scorer

def compute_score(
    payload: MetricsPayload,
    baseline: Optional[dict] = None,
) -> ScoreResult:
    """
    Compute server-authoritative fatigue score from raw behavioral metrics.

    Returns structured reasons (ranked by impact), contribution breakdown,
    and the classic flat reasons list for backward compatibility.

    When a baseline dict is supplied and trusted (>= MIN_BASELINE_SAMP),
    scoring shifts from population norms to personal deviation.
    """
    p = payload
    baseline_trusted = (
        baseline is not None
        and baseline.get("sample_count", 0) >= MIN_BASELINE_SAMP
        and baseline.get("typing_speed", 0) > 0
    )

    # Guard: not enough data
    if p.key_count < 5:
        return ScoreResult(
            score=0,
            performance_score=100,
            level=FatigueLevel.INACTIVE,
            cognitive_state=CognitiveState.INACTIVE,
            coach="Start typing to begin monitoring.",
            reasons=[],
            structured_reasons=[],
            contribution=None,
            recovery_action=None,
            baseline_used=False,
            institution_mode=p.institution_mode,
        )

    flat_reasons: list[str] = []

    # ── Feature 1: typing speed ──
    if baseline_trusted:
        bl_speed = baseline["typing_speed"]
        drop = (bl_speed - p.typing_speed) / max(bl_speed, 1)
        speed_norm = _clamp(drop / 0.6, 0.0, 1.0)
        speed_desc = f"Typing speed {round(drop * 100)}% below baseline ({round(p.typing_speed)} cpm)"
    else:
        speed_norm = _norm(p.typing_speed, 400, 80)
        speed_desc = f"Typing speed at {round(p.typing_speed)} cpm"
    if speed_norm > 0.5:
        flat_reasons.append(speed_desc)

    # ── Feature 2: error rate ──
    if baseline_trusted:
        bl_err = max(baseline["error_rate"], 0.01)
        rise = (p.error_rate - bl_err) / bl_err
        error_norm = _clamp(rise / 4.0, 0.0, 1.0)
        error_desc = f"Error rate {round(p.error_rate / bl_err, 1)}x baseline ({round(p.error_rate * 100)}%)"
    else:
        error_norm = _norm(p.error_rate, 0.0, 0.25, invert=True)
        error_desc = f"Error rate at {round(p.error_rate * 100)}%"
    if error_norm > 0.4:
        flat_reasons.append(error_desc)

    # ── Feature 3: avg latency (+ burstiness folded in) ──
    bursty_boost = _clamp(_norm(p.burstiness, 50, 500, invert=True) * 0.2, 0.0, 0.2)
    if baseline_trusted:
        bl_lat = max(baseline["avg_latency"], 1)
        rise = (p.avg_latency - bl_lat) / bl_lat
        latency_norm = _clamp(rise / 1.5 + bursty_boost, 0.0, 1.0)
        latency_desc = f"Response time {round(p.avg_latency)}ms (baseline: {round(bl_lat)}ms)"
    else:
        latency_norm = _clamp(_norm(p.avg_latency, 100, 600, invert=True) + bursty_boost, 0.0, 1.0)
        latency_desc = f"Keystroke latency at {round(p.avg_latency)}ms"
    if latency_norm > 0.5:
        flat_reasons.append(latency_desc)

    # ── Feature 4: tab switches ──
    switch_norm = _norm(p.tab_switches, 0, 12, invert=True)
    switch_desc = f"{p.tab_switches} tab switches — context fragmentation"
    if switch_norm > 0.5:
        flat_reasons.append(switch_desc)

    # ── Session fatigue amplifier: >2h sessions amplify signal ──
    session_hours = p.session_duration_s / 3600
    session_mod = min(0.15, max(0.0, (session_hours - 2.0) * 0.05))
    if session_mod > 0.05:
        flat_reasons.append(f"Extended session ({round(session_hours, 1)}h) amplifying fatigue")

    # ── Idle reducer ──
    idle_factor = 0.1 if p.idle_time_ms > 10_000 else 0.0

    # ── Weighted combination (4-factor model) ──
    raw = (
        W_TYPING  * speed_norm  +
        W_ERROR   * error_norm  +
        W_LATENCY * latency_norm +
        W_TABS    * switch_norm
    )

    score = round(_clamp((raw + session_mod - idle_factor) * 100, 0, 100), 1)
    performance_score = round(100 - score, 1)

    # ── Build structured reasons (ranked by impact) ──
    factor_data = [
        ("typing",       W_TYPING,  speed_norm,   p.typing_speed,  speed_desc),
        ("error_rate",   W_ERROR,   error_norm,   p.error_rate,    error_desc),
        ("latency",      W_LATENCY, latency_norm, p.avg_latency,   latency_desc),
        ("tab_switching", W_TABS,   switch_norm,  p.tab_switches,  switch_desc),
    ]

    structured_reasons = []
    for factor_name, weight, norm_val, raw_val, desc in factor_data:
        impact_pts = round(weight * norm_val * 100, 1)
        if impact_pts > 2:  # only include meaningful contributors
            structured_reasons.append(ReasonFactor(
                factor=factor_name,
                impact=f"+{impact_pts}",
                weight=weight,
                description=desc,
            ))

    # Sort by impact (highest first), cap at top 3
    structured_reasons.sort(key=lambda r: float(r.impact.replace("+", "")), reverse=True)
    structured_reasons = structured_reasons[:3]

    # ── Build contribution dict ──
    total_weighted = sum(w * n for _, w, n, _, _ in factor_data) or 1
    contribution = {}
    for factor_name, weight, norm_val, raw_val, _ in factor_data:
        pct = round((weight * norm_val / total_weighted) * 100)
        contribution[factor_name] = {
            "pct": pct,
            "norm": round(norm_val, 3),
            "raw": round(raw_val, 2) if isinstance(raw_val, float) else raw_val,
        }

    # ── Level + coach + recovery action ──
    level, coach, recovery = _label_and_recover(
        score, p, baseline_trusted, baseline,
        speed_norm, error_norm, latency_norm, switch_norm
    )

    return ScoreResult(
        score=score,
        performance_score=performance_score,
        level=level,
        cognitive_state=CognitiveState(level.value),
        coach=coach,
        recovery_action=recovery,
        reasons=flat_reasons,
        structured_reasons=structured_reasons,
        contribution=contribution,
        baseline_used=baseline_trusted,
        institution_mode=p.institution_mode,
    )


def _label_and_recover(
    score: float,
    p: MetricsPayload,
    bl_trusted: bool,
    baseline: Optional[dict],
    speed_norm: float,
    error_norm: float,
    latency_norm: float,
    switch_norm: float,
) -> tuple[FatigueLevel, str, Optional[RecoveryAction]]:
    pers = " (vs your baseline)" if bl_trusted else ""

    if score >= FATIGUE_HIGH:
        level = FatigueLevel.HIGH
        signals = []
        if error_norm > 0.6:
            signals.append("error rate spiked")
        if latency_norm > 0.6:
            signals.append("response time slowed")
        if speed_norm > 0.6:
            signals.append(f"speed dropped to {round(p.typing_speed)} cpm")
        if switch_norm > 0.6:
            signals.append(f"{p.tab_switches} tab switches")
        detail = " -- " + ", ".join(signals) if signals else ""
        coach = f"High cognitive load{detail}. Take a 3-minute break now."
        recovery = RecoveryAction(
            action="3-minute guided reset",
            duration_min=3,
            type="break",
            url="https://www.calm.com/breathe",
        )

    elif score >= FATIGUE_ELEVATED:
        level = FatigueLevel.ELEVATED
        coach = (
            f"Mental load rising above your baseline (score {score})." if bl_trusted
            else f"Mental load rising (score {score}). Consider a short pause."
        )
        recovery = RecoveryAction(
            action="Finish current task, then take a 2-minute micro-break",
            duration_min=2,
            type="micro_break",
        )

    else:
        level = FatigueLevel.NORMAL
        if bl_trusted:
            coach = ("Peak state -- performing above your personal baseline."
                     if score < 20 else "Within your normal range. Keep it up!")
        else:
            coach = "Optimal performance state." if score < 20 else "Cognitive load manageable."
        recovery = RecoveryAction(
            action="No action needed",
            duration_min=0,
            type="none",
        )

    return level, coach, recovery


# Cognitive state overlay (deep focus detection)

def detect_cognitive_state(
    result: ScoreResult,
    payload: MetricsPayload,
    deep_focus_streak: int,
) -> tuple[ScoreResult, int]:
    """
    Post-scoring overlay. Upgrades NORMAL -> DEEP_FOCUS when:
      - <=1 tab switches
      - error_rate < 8%
      - fatigue score < 50
      - active_time_ratio > 60%
    Returns updated result and new streak counter.
    """
    if payload.key_count < 10:
        result.cognitive_state = CognitiveState.INACTIVE
        return result, 0

    is_deep = (
        payload.tab_switches <= 1
        and payload.error_rate < 0.08
        and result.score < 50
        and payload.active_time_ratio > 0.6
    )

    if is_deep:
        new_streak = deep_focus_streak + 1
        streak_mins = round((new_streak * 30) / 60, 1)
        result.cognitive_state = CognitiveState.DEEP_FOCUS
        result.focus_streak_mins = streak_mins
        result.level = FatigueLevel.DEEP_FOCUS
        result.coach = (
            f"Deep focus -- {streak_mins}m flow state. Zero interruptions, low error rate."
            if streak_mins >= 2
            else "Entering deep focus state. Protect this window."
        )
        result.recovery_action = RecoveryAction(
            action="Stay in flow -- no break needed",
            duration_min=0,
            type="none",
        )
        return result, new_streak

    return result, 0


# Trend analysis

def analyse_trend(recent_scores: list[float]) -> TrendAnalysis:
    """
    Given the last N fatigue scores (chronological, most recent last).
    Returns rolling average, direction, burnout risk, and a recommendation.
    """
    if not recent_scores:
        return TrendAnalysis(
            trend_score=0,
            direction="STABLE",
            burnout_risk=False,
            sustained_high=0,
            recommendation="Not enough data yet.",
        )

    n = min(len(recent_scores), TREND_WINDOW)
    window = recent_scores[-n:]
    trend_score = round(sum(window) / n, 1)

    # Direction: compare first half vs second half
    if len(window) >= 4:
        mid = len(window) // 2
        first_avg = sum(window[:mid]) / mid
        second_avg = sum(window[mid:]) / (len(window) - mid)
        delta = second_avg - first_avg
        direction = "WORSENING" if delta > 8 else ("IMPROVING" if delta < -8 else "STABLE")
    else:
        direction = "STABLE"

    # Sustained HIGH count (consecutive from the end)
    sustained_high = 0
    for s in reversed(window):
        if s >= FATIGUE_HIGH:
            sustained_high += 1
        else:
            break

    burnout_risk = sustained_high >= BURNOUT_WINDOW

    # Velocity: rate of score change per window
    if len(window) >= 3:
        velocity = round((window[-1] - window[0]) / max(len(window) - 1, 1), 1)
    else:
        velocity = 0.0

    # Burnout trajectory: compare sustained_high now vs earlier
    if len(recent_scores) >= 10:
        older_window = recent_scores[-10:-5]
        older_sustained = sum(1 for s in older_window if s >= FATIGUE_HIGH)
        if sustained_high > older_sustained:
            burnout_trajectory = "increasing"
        elif sustained_high < older_sustained:
            burnout_trajectory = "decreasing"
        else:
            burnout_trajectory = "stable"
    else:
        burnout_trajectory = "stable"

    if burnout_risk:
        rec = (f"Burnout risk -- {sustained_high} consecutive high-load windows. "
               "Take a 10+ minute break and avoid deep cognitive work.")
    elif direction == "WORSENING" and trend_score > FATIGUE_ELEVATED:
        rec = "Load trending upward. Wrap up current task and take a short break."
    elif direction == "IMPROVING":
        rec = "Load decreasing -- recovery is working. Re-engage when ready."
    elif trend_score < FATIGUE_ELEVATED:
        rec = "Sustained healthy cognitive load. Good pacing."
    else:
        rec = "Elevated but stable. Monitor over next 10 minutes."

    return TrendAnalysis(
        trend_score=trend_score,
        direction=direction,
        burnout_risk=burnout_risk,
        sustained_high=sustained_high,
        recommendation=rec,
        burnout_trajectory=burnout_trajectory,
        velocity=velocity,
    )


# Baseline EMA update

def update_baseline_ema(
    current: Optional[dict],
    payload: MetricsPayload,
) -> Optional[dict]:
    """
    Returns updated baseline dict (typing_speed, avg_latency, error_rate, sample_count).
    Returns None if this window doesn't qualify (not enough keys or too slow).
    """
    if payload.key_count < 10 or payload.typing_speed < 20:
        return None

    alpha = BASELINE_ALPHA

    if current is None or current.get("sample_count", 0) == 0:
        return {
            "typing_speed": payload.typing_speed,
            "avg_latency":  payload.avg_latency,
            "error_rate":   payload.error_rate,
            "sample_count": 1,
        }

    return {
        "typing_speed": alpha * payload.typing_speed + (1 - alpha) * current["typing_speed"],
        "avg_latency":  alpha * payload.avg_latency  + (1 - alpha) * current["avg_latency"],
        "error_rate":   alpha * payload.error_rate   + (1 - alpha) * current["error_rate"],
        "sample_count": current["sample_count"] + 1,
    }
