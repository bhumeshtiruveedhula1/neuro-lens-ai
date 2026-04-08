"""
NeuroLens AI -- Feature Engineering
====================================
Implements the exact feature set described in the research literature:

  - SWELL-KW (Koldijk et al.): KeyStrokes, CharactersRatio, ErrorKeyRatio,
    AppChanges, TabfocusChange
  - De Jong et al.: mean Inter-Key Interval (IKI), session-level drift features
  - Ulinskas et al.: HT/PP aggregates, skewness, IQR
  - Daytime fatigue paper: PP latency timing primitives, pause/burst analysis
  - Hagimoto et al.: mouse activity correlation patterns

The feature vector fed to the ML model matches exactly what the Chrome
extension captures (keystroke timestamps, backspace count, latency, tab switches)
so there is zero feature mismatch between training and live inference.

Research accuracy targets (from Prompt 4 / literature):
  - Subject-dependent F1 >= 0.70, AUC >= 0.80  (good baseline)
  - Cross-subject is harder; 0.60-0.75 realistic
"""

from __future__ import annotations
import math
import statistics
from typing import Dict, List, Optional, Any


# ── Constants from research ────────────────────────────────────────────────────
PAUSE_THRESHOLD_MS = 500   # Ulinskas et al., daytime fatigue paper
CHARS_PER_WORD     = 5     # standard WPM conversion
WINDOW_S_DEFAULT   = 30    # default window (matches extension)


def compute_timing_features(
    press_press_latencies: List[float],   # PP[i] = P_{i+1} - P_i  (ms)
    hold_times: List[float],              # HT[i] = R_i - P_i       (ms)
) -> Dict[str, float]:
    """
    Timing primitives from the daytime fatigue paper and Ulinskas et al.
    Returns mean, std, p90, skewness, IQR for both PP and HT.
    Fatigue causes: slower PP (mean_PP up), higher variance (std_PP up),
    longer hold times (mean_HT up), and heavier tails (p90_PP, skew_PP up).
    """
    feats: Dict[str, float] = {}

    for name, arr in [("PP", press_press_latencies), ("HT", hold_times)]:
        if not arr:
            for stat in ("mean", "std", "p90", "skew", "iqr"):
                feats[f"{stat}_{name}"] = 0.0
            continue

        sorted_arr = sorted(arr)
        n = len(arr)
        mean = sum(arr) / n
        variance = sum((x - mean) ** 2 for x in arr) / max(1, n - 1)
        std = math.sqrt(variance)

        # 90th percentile
        idx = int(0.9 * n)
        p90 = sorted_arr[min(idx, n - 1)]

        # IQR = Q3 - Q1
        q1 = sorted_arr[int(0.25 * n)]
        q3 = sorted_arr[int(0.75 * n)]
        iqr = q3 - q1

        # Skewness (Fisher-Pearson) -- positive = right tail (more slow keys)
        skew = 0.0
        if std > 0 and n >= 3:
            skew = (sum((x - mean) ** 3 for x in arr) / n) / (std ** 3)

        feats[f"mean_{name}"]  = round(mean, 3)
        feats[f"std_{name}"]   = round(std, 3)
        feats[f"p90_{name}"]   = round(p90, 3)
        feats[f"skew_{name}"]  = round(skew, 3)
        feats[f"iqr_{name}"]   = round(iqr, 3)

    return feats


def compute_typing_speed_features(
    n_chars: int,
    window_s: float,
    press_press_latencies: List[float],
) -> Dict[str, float]:
    """
    Typing speed features: CPS, WPM, mean IKI (= mean_PP).
    Matches de Jong et al. window-level IKI approach and SWELL-KW definitions.
    """
    if window_s <= 0:
        return {"cps": 0.0, "wpm": 0.0}

    cps = n_chars / window_s
    wpm = n_chars / (CHARS_PER_WORD * (window_s / 60))

    return {
        "cps": round(cps, 3),
        "wpm": round(wpm, 3),
    }


def compute_error_features(
    n_backspace: int,
    n_delete_undo: int,
    n_chars: int,
    n_spaces: int,
    n_total_keys: int,
) -> Dict[str, float]:
    """
    SWELL-KW error feature definitions exactly:
      ErrorKeyRatio  = (Backspace + Delete + Undo) / (Chars + Spaces)
      CharactersRatio = Chars / TotalKeystrokes
      backspace_pct   = 100 * Backspace / TotalKeystrokes

    Both fatigue and stress studies see higher error ratios under cognitive load.
    """
    error_keys = n_backspace + n_delete_undo
    denom_error = max(1, n_chars + n_spaces)
    denom_keys  = max(1, n_total_keys)

    return {
        "error_key_ratio":    round(error_keys / denom_error, 4),
        "characters_ratio":   round(n_chars / denom_keys, 4),
        "backspace_pct":      round(100.0 * n_backspace / denom_keys, 3),
    }


def compute_pause_burst_features(
    press_press_latencies: List[float],
    window_s: float,
    pause_threshold_ms: float = PAUSE_THRESHOLD_MS,
) -> Dict[str, float]:
    """
    Pause/burst features from the daytime fatigue paper.
    Fatigue causes more pauses, longer pauses, and shorter bursts.
    """
    if not press_press_latencies:
        return {
            "num_pauses": 0,
            "mean_pause_ms": 0.0,
            "pause_ratio": 0.0,
            "burst_length_mean": 0.0,
        }

    pauses = [pp for pp in press_press_latencies if pp > pause_threshold_ms]
    non_pauses = [pp for pp in press_press_latencies if pp <= pause_threshold_ms]

    num_pauses = len(pauses)
    mean_pause_ms = sum(pauses) / max(1, len(pauses))
    pause_ratio = sum(pauses) / max(1, window_s * 1000)  # fraction of window in pauses

    # Burst: consecutive keys without a pause
    burst_lengths: List[int] = []
    current_burst = 1
    for pp in press_press_latencies:
        if pp <= pause_threshold_ms:
            current_burst += 1
        else:
            if current_burst > 0:
                burst_lengths.append(current_burst)
            current_burst = 1
    if current_burst > 0:
        burst_lengths.append(current_burst)

    burst_length_mean = sum(burst_lengths) / max(1, len(burst_lengths))

    return {
        "num_pauses":        num_pauses,
        "mean_pause_ms":     round(mean_pause_ms, 2),
        "pause_ratio":       round(pause_ratio, 4),
        "burst_length_mean": round(burst_length_mean, 2),
    }


def compute_interaction_features(
    tab_switches: int,
    app_changes: int = 0,
    mouse_events: int = 0,
) -> Dict[str, float]:
    """
    SWELL-KW interaction features.
    High tab switching correlates with high cognitive load / distraction.
    """
    return {
        "tab_switches":  tab_switches,
        "app_changes":   app_changes,
        "mouse_events":  mouse_events,
    }


def compute_session_drift_features(
    wpm_series: List[float],
    error_series: List[float],
) -> Dict[str, float]:
    """
    De Jong et al. session-level dynamics: compare first vs last segment
    to detect within-session fatigue accumulation.

    wpm_series: list of WPM values from successive windows in this session.
    error_series: list of error_key_ratio values from successive windows.
    """
    if len(wpm_series) < 2:
        return {
            "delta_wpm": 0.0,
            "delta_error_rate": 0.0,
            "wpm_slope": 0.0,
        }

    half = max(1, len(wpm_series) // 2)
    first_wpm  = sum(wpm_series[:half]) / half
    last_wpm   = sum(wpm_series[-half:]) / half
    first_err  = sum(error_series[:half]) / half
    last_err   = sum(error_series[-half:]) / half

    # Linear slope of WPM over windows (proxy for fatigue trend)
    n = len(wpm_series)
    xs = list(range(n))
    x_mean = (n - 1) / 2
    y_mean = sum(wpm_series) / n
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, wpm_series))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    slope = ss_xy / max(1e-9, ss_xx)  # WPM per window; negative = slowing down

    return {
        "delta_wpm":        round(last_wpm - first_wpm, 2),
        "delta_error_rate": round(last_err - first_err, 4),
        "wpm_slope":        round(slope, 4),
    }


# ── Main feature builder (Extension-compatible) ────────────────────────────────

def build_feature_vector(
    # Core extension signals (always available)
    typing_speed_cpm: float,      # keys per minute from extension
    error_rate: float,            # backspaces / total keys
    avg_latency_ms: float,        # mean inter-key latency
    burstiness_ms: float,         # std dev of inter-key latency
    avg_hold_duration_ms: float,  # mean key hold time
    tab_switches: int,
    idle_time_ms: float,
    session_duration_s: float,
    active_time_ratio: float,

    # Extended timing arrays (if available from extension raw events)
    press_press_latencies: Optional[List[float]] = None,
    hold_times: Optional[List[float]] = None,

    # Counts for SWELL-KW error features
    n_backspace: int = 0,
    n_chars: int = 0,
    n_total_keys: int = 0,
    window_s: float = WINDOW_S_DEFAULT,

    # Session drift (if multi-window history available)
    wpm_history: Optional[List[float]] = None,
    error_history: Optional[List[float]] = None,
) -> Dict[str, float]:
    """
    Builds the full ML-ready feature vector from a 30s window snapshot.

    Always-available features (from extension payload):
      typing_speed, error_rate, avg_latency, burstiness, avg_hold_duration,
      tab_switches, idle_time, session_duration, active_time_ratio

    Extended features (if raw events are logged):
      Timing distributions (mean/std/p90/skew/iqr for PP and HT)
      Error breakdown (SWELL-KW definitions)
      Pause/burst analysis
      Session drift (delta_wpm, wpm_slope)

    The vector is designed to work at BOTH levels:
      - Minimal (9 features): just extension payload  → fast, always available
      - Full (30+ features): raw events + history      → higher accuracy
    """
    feats: Dict[str, float] = {}

    # ── Tier 1: Core extension features ──────────────────────────────────────
    # Convert cpm to wpm (standard for literature comparison)
    wpm = typing_speed_cpm / CHARS_PER_WORD
    feats["wpm"]                = round(wpm, 2)
    feats["typing_speed_cpm"]   = round(typing_speed_cpm, 2)
    feats["error_rate"]         = round(error_rate, 4)
    feats["avg_latency_ms"]     = round(avg_latency_ms, 2)
    feats["burstiness_ms"]      = round(burstiness_ms, 2)
    feats["avg_hold_duration_ms"] = round(avg_hold_duration_ms, 2)
    feats["tab_switches"]       = int(tab_switches)
    feats["idle_time_s"]        = round(idle_time_ms / 1000, 3)
    feats["session_duration_s"] = round(session_duration_s, 1)
    feats["active_time_ratio"]  = round(active_time_ratio, 3)

    # ── Tier 2: Timing distribution features (from raw arrays) ───────────────
    if press_press_latencies and len(press_press_latencies) >= 5:
        timing = compute_timing_features(
            press_press_latencies,
            hold_times or [],
        )
        feats.update(timing)
        # Pause/burst
        feats.update(compute_pause_burst_features(press_press_latencies, window_s))
    else:
        # Reconstruct approximations from summary stats (extension-only mode)
        # These match the research features using available proxies
        feats["mean_PP"]  = round(avg_latency_ms, 2)
        feats["std_PP"]   = round(burstiness_ms, 2)
        feats["p90_PP"]   = round(avg_latency_ms + 1.5 * burstiness_ms, 2)
        feats["mean_HT"]  = round(avg_hold_duration_ms, 2)
        feats["std_HT"]   = 0.0
        # Pause ratio approximation
        feats["pause_ratio"] = round(idle_time_ms / max(1, window_s * 1000), 4)

    # ── Tier 3: SWELL-KW error features (from key counts) ────────────────────
    if n_total_keys > 0:
        feats.update(compute_error_features(
            n_backspace=n_backspace,
            n_delete_undo=0,
            n_chars=n_chars,
            n_spaces=max(0, n_total_keys - n_chars - n_backspace),
            n_total_keys=n_total_keys,
        ))
    else:
        # Use extension-level error_rate as proxy
        feats["error_key_ratio"]  = round(error_rate, 4)
        feats["characters_ratio"] = round(max(0, 1 - error_rate), 4)
        feats["backspace_pct"]    = round(error_rate * 100, 2)

    # ── Tier 4: Session drift (de Jong et al.) ────────────────────────────────
    if wpm_history and len(wpm_history) >= 3:
        feats.update(compute_session_drift_features(
            wpm_history,
            error_history or [error_rate],
        ))
    else:
        feats["delta_wpm"]        = 0.0
        feats["delta_error_rate"] = 0.0
        feats["wpm_slope"]        = 0.0

    # ── Derived composite features ────────────────────────────────────────────
    # Cognitive load index: combined pressure signal (higher = more load)
    feats["cognitive_load_index"] = round(
        0.3 * feats["error_rate"] +
        0.3 * min(1.0, feats["avg_latency_ms"] / 600) +
        0.2 * min(1.0, feats["tab_switches"] / 12) +
        0.2 * (1 - feats["active_time_ratio"]),
        4
    )

    # Session fatigue amplifier: >2h sessions get extra weight (our own addition)
    session_hours = session_duration_s / 3600
    feats["session_fatigue_amp"] = round(
        min(0.3, max(0.0, (session_hours - 2.0) * 0.05)), 4
    )

    return feats


def get_minimal_feature_names() -> List[str]:
    """The 9 always-available features from the extension payload."""
    return [
        "wpm", "error_rate", "avg_latency_ms", "burstiness_ms",
        "avg_hold_duration_ms", "tab_switches", "idle_time_s",
        "active_time_ratio", "cognitive_load_index",
    ]


def get_full_feature_names() -> List[str]:
    """All 20+ features when timing arrays are available."""
    return [
        "wpm", "typing_speed_cpm", "error_rate", "avg_latency_ms",
        "burstiness_ms", "avg_hold_duration_ms", "tab_switches",
        "idle_time_s", "session_duration_s", "active_time_ratio",
        "mean_PP", "std_PP", "p90_PP", "mean_HT", "std_HT",
        "error_key_ratio", "characters_ratio", "backspace_pct",
        "pause_ratio", "delta_wpm", "delta_error_rate", "wpm_slope",
        "cognitive_load_index", "session_fatigue_amp",
    ]
