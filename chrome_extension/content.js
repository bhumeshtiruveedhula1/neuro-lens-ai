(function () {
  "use strict";

  const WINDOW_MS = 60 * 1000;
  const IDLE_THRESHOLD_MS = 3000;

  const state = {
    windowStart: Date.now(),
    keyCount: 0,
    characterCount: 0,
    backspaceCount: 0,
    interkeyLatencies: [],
    keyHoldDurations: [],
    keydownTimestamps: {},
    lastKeydownAt: null,
    lastActivityAt: Date.now(),
    activeStartedAt: null,
    activeSeconds: 0,
    typingActiveSeconds: 0,
    idleBursts: 0,
    idleOpen: false,
  };

  function average(values) {
    if (!values.length) return 0;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function std(values) {
    if (values.length < 2) return 0;
    const mean = average(values);
    const variance = values.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / values.length;
    return Math.sqrt(variance);
  }

  function isShortVideoPath() {
    const path = window.location.pathname.toLowerCase();
    return path.includes("/shorts") || path.includes("/reels") || path.includes("/clip") || window.location.hostname.includes("tiktok.com");
  }

  function markActive(now) {
    state.lastActivityAt = now;
    if (state.activeStartedAt === null) {
      state.activeStartedAt = now;
    }
    if (state.idleOpen) {
      state.idleOpen = false;
    }
  }

  function flushActive(now) {
    if (state.activeStartedAt !== null) {
      state.activeSeconds += (now - state.activeStartedAt) / 1000;
      state.activeStartedAt = null;
    }
  }

  document.addEventListener("keydown", (event) => {
    const now = Date.now();
    markActive(now);
    state.keydownTimestamps[event.code] = now;
    state.keyCount += 1;
    if (event.key.length === 1) {
      state.characterCount += 1;
      state.typingActiveSeconds += 1.2;
    }
    if (event.key === "Backspace") {
      state.backspaceCount += 1;
    }
    if (state.lastKeydownAt !== null) {
      const latency = now - state.lastKeydownAt;
      if (latency < 5000) {
        state.interkeyLatencies.push(latency);
      }
    }
    state.lastKeydownAt = now;
  }, true);

  document.addEventListener("keyup", (event) => {
    const now = Date.now();
    const downAt = state.keydownTimestamps[event.code];
    if (downAt !== undefined) {
      const hold = now - downAt;
      if (hold > 0 && hold < 1000) {
        state.keyHoldDurations.push(hold);
      }
      delete state.keydownTimestamps[event.code];
    }
  }, true);

  ["mousemove", "click", "scroll"].forEach((name) => {
    document.addEventListener(name, () => markActive(Date.now()), { passive: true });
  });

  setInterval(() => {
    const now = Date.now();
    if (now - state.lastActivityAt > IDLE_THRESHOLD_MS) {
      if (!state.idleOpen) {
        state.idleBursts += 1;
        state.idleOpen = true;
      }
      flushActive(now);
    }
  }, 2000);

  function buildSnapshot(now) {
    flushActive(now);
    const elapsedSeconds = Math.max(1, Math.round((now - state.windowStart) / 1000));
    const idleSeconds = Math.max(0, elapsedSeconds - state.activeSeconds);
    const shortVideoSeconds = isShortVideoPath() ? state.activeSeconds : 0;

    return {
      timestamp: new Date(now).toISOString(),
      window_duration_s: elapsedSeconds,
      app_name: "browser",
      active_domain: window.location.hostname,
      active_path: window.location.pathname,
      page_title: document.title,
      key_count: state.keyCount,
      character_count: state.characterCount,
      backspace_count: state.backspaceCount,
      mean_key_hold: Number(average(state.keyHoldDurations).toFixed(4)),
      std_key_hold: Number(std(state.keyHoldDurations).toFixed(4)),
      key_hold_samples: state.keyHoldDurations.length,
      mean_interkey_latency: Number(average(state.interkeyLatencies).toFixed(4)),
      std_interkey_latency: Number(std(state.interkeyLatencies).toFixed(4)),
      interkey_samples: state.interkeyLatencies.length,
      typing_active_seconds: Number(Math.min(elapsedSeconds, state.typingActiveSeconds).toFixed(2)),
      active_seconds: Number(Math.min(elapsedSeconds, state.activeSeconds).toFixed(2)),
      idle_seconds: Number(idleSeconds.toFixed(2)),
      idle_bursts: state.idleBursts,
      tab_switches: 0,
      window_switches: 0,
      short_video_seconds: Number(shortVideoSeconds.toFixed(2)),
      short_video_sessions: shortVideoSeconds > 0 ? 1 : 0,
    };
  }

  function resetWindow(now) {
    state.windowStart = now;
    state.keyCount = 0;
    state.characterCount = 0;
    state.backspaceCount = 0;
    state.interkeyLatencies = [];
    state.keyHoldDurations = [];
    state.typingActiveSeconds = 0;
    state.activeSeconds = 0;
    state.idleBursts = 0;
    state.activeStartedAt = now;
    state.idleOpen = false;
  }

  function sendSnapshot() {
    const now = Date.now();
    const snapshot = buildSnapshot(now);
    resetWindow(now);
    if (!chrome.runtime?.id) return;
    chrome.runtime.sendMessage({
      type: "TAB_MINUTE_SNAPSHOT",
      data: snapshot,
    }).catch(() => {});
  }

  setInterval(sendSnapshot, WINDOW_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      sendSnapshot();
    }
  });
})();
