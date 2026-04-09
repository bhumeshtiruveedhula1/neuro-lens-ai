import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlarmClock, Bot, Brain, Gauge, ListFilter, Moon, PlayCircle, ShieldCheck, Sparkles, Sun } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

const API_BASE = "http://localhost:8001";
const USER_ID = "default";
const WS_URL = `ws://localhost:8001/ws/live?user_id=${USER_ID}`;

const VIEWS = [
  { id: "dashboard", label: "Dashboard", icon: Gauge },
  { id: "typing", label: "Typing Lab", icon: Activity },
  { id: "video", label: "Video Tracker", icon: PlayCircle },
  { id: "alerts", label: "Alerts", icon: AlarmClock },
  { id: "activity", label: "App Breakdown", icon: Sparkles },
  { id: "onboarding", label: "Onboarding + EMA", icon: ListFilter },
  { id: "explainability", label: "Confidence", icon: Brain },
];

const defaultProfile = {
  baseline_fatigue_week: 35,
  baseline_stress_week: 35,
  current_fatigue: 30,
  current_stress: 30,
  focus_capacity_minutes: 75,
  break_style: "balanced",
  user_target_hours: 6,
  preferred_break_habit: "balanced",
  video_use_effect: "mixed",
  productivity_goal: "",
  focus_apps: "",
  distraction_apps: "",
  onboarding_complete: false,
};

const PLATFORM_LABELS = {
  youtube_shorts: "YouTube Shorts",
  instagram_reels: "Instagram Reels",
  tiktok: "TikTok",
};

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const mean = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0);
const std = (arr) => {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
};

function stateColor(label) {
  if (label === "Burnout Risk") return "#cb7d7d";
  if (label === "Fatigued") return "#c6a06e";
  if (label === "High Load") return "#bcb58c";
  return "#7eb99a";
}

function toFormProfile(profile) {
  const raw = profile || defaultProfile;
  return {
    ...defaultProfile,
    ...raw,
    focus_apps: (raw.focus_apps || []).join(", "),
    distraction_apps: (raw.distraction_apps || []).join(", "),
  };
}

function fetchJson(path, fallback) {
  return fetch(`${API_BASE}${path}`)
    .then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    })
    .catch(() => fallback);
}

function TrustLine() {
  return (
    <div className="trust-line">
      <ShieldCheck size={15} />
      <p>Privacy-first: behavior metadata only. No typed text storage, no screenshots, no content scraping.</p>
    </div>
  );
}

function ScoreRing({ value, label }) {
  const score = clamp(Math.round(value || 0), 0, 100);
  const color = stateColor(label);
  return (
    <div className="score-ring">
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="50" className="ring-bg" />
        <circle cx="60" cy="60" r="50" className="ring-fill" style={{ stroke: color, strokeDasharray: `${(score / 100) * 314} 314` }} />
      </svg>
      <div>
        <strong>{score}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function ChatWidget({ open, unread, messages, onToggle, onSend, onQuickReply, input, setInput }) {
  return (
    <div className={`chat-shell ${open ? "open" : ""}`}>
      <button className="chat-fab" onClick={onToggle}>
        <Bot size={15} />
        <span>Companion</span>
        {unread > 0 && <b>{unread}</b>}
      </button>
      {open && (
        <div className="chat-panel">
          <div className="chat-head">
            <strong>NeuroLens Companion</strong>
            <span>Supportive and non-judgmental</span>
          </div>
          <div className="chat-body">
            {messages.map((m) => (
              <div key={m.id} className={`bubble ${m.role}`}>
                <p>{m.text}</p>
                {!!m.quick_replies?.length && (
                  <div className="quick-row">
                    {m.quick_replies.map((q) => (
                      <button key={q.id} className="quick-btn" onClick={() => onQuickReply(q.action, q.payload || {})}>
                        {q.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <form className="chat-input-row" onSubmit={(e) => { e.preventDefault(); onSend(); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="How are you feeling?" />
            <button type="submit">Send</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState("dashboard");
  const [theme, setTheme] = useState(localStorage.getItem("neurolens-theme") || "dark");
  const [demoMode, setDemoMode] = useState(false);
  const [state, setState] = useState(null);
  const [history, setHistory] = useState([]);
  const [profile, setProfile] = useState(defaultProfile);
  const [notifications, setNotifications] = useState([]);
  const [calibration, setCalibration] = useState(null);
  const [telemetryPoints, setTelemetryPoints] = useState([]);
  const [videoSummary, setVideoSummary] = useState(null);
  const [videoSessions, setVideoSessions] = useState([]);
  const [chat, setChat] = useState([]);
  const [unread, setUnread] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");

  const [videoForm, setVideoForm] = useState({ platform: "youtube_shorts", duration_min: 6, in_focus_block: false, note: "" });
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [savingProfile, setSavingProfile] = useState(false);
  const [ema, setEma] = useState({ fatigue: 4, stress: 4, focus: 6 });

  const [labText, setLabText] = useState("");
  const [labStartedAt, setLabStartedAt] = useState(null);
  const [labTick, setLabTick] = useState(Date.now());
  const [labKeyCount, setLabKeyCount] = useState(0);
  const [labCharCount, setLabCharCount] = useState(0);
  const [labBackspaceCount, setLabBackspaceCount] = useState(0);
  const [labLatencies, setLabLatencies] = useState([]);
  const [labHolds, setLabHolds] = useState([]);
  const [labPrediction, setLabPrediction] = useState(null);
  const downMapRef = useRef({});
  const lastKeyDownRef = useRef(null);
  const [demoState, setDemoState] = useState(null);
  const [demoHistory, setDemoHistory] = useState([]);
  const [demoVideoSummary, setDemoVideoSummary] = useState(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("neurolens-theme", theme);
  }, [theme]);

  async function loadAll(markRead = false) {
    const [p, s, h, n, c, t, vs, vlist, tr] = await Promise.all([
      fetchJson(`/profile/onboarding?user_id=${USER_ID}`, { profile: defaultProfile }),
      fetchJson(`/state/latest?user_id=${USER_ID}`, null),
      fetchJson(`/metrics/history?user_id=${USER_ID}&limit=90`, { points: [] }),
      fetchJson(`/notifications?user_id=${USER_ID}`, { notifications: [] }),
      fetchJson(`/calibration/status?user_id=${USER_ID}`, null),
      fetchJson(`/chat/thread?user_id=${USER_ID}&mark_read=${markRead ? "true" : "false"}`, { messages: [], unread_count: 0 }),
      fetchJson(`/video-sessions/summary?user_id=${USER_ID}`, { by_platform_min: {}, insights: [] }),
      fetchJson(`/video-sessions?user_id=${USER_ID}&limit=50`, { sessions: [] }),
      fetchJson(`/telemetry/recent?user_id=${USER_ID}&limit=60`, { points: [] }),
    ]);
    setProfile(toFormProfile(p.profile));
    setState(s);
    setHistory(h.points || []);
    setNotifications(n.notifications || []);
    setCalibration(c);
    setChat(t.messages || []);
    setUnread(t.unread_count || 0);
    setVideoSummary(vs);
    setVideoSessions(vlist.sessions || []);
    setTelemetryPoints(tr.points || []);
  }

  useEffect(() => { loadAll().catch(() => {}); }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => ws.send("ready");
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "LIVE_STATE") {
        setState(payload);
        setHistory((cur) => [...cur.slice(-89), { timestamp: payload.timestamp, fatigue_score: payload.fatigue_score, load_score: payload.load_score }]);
      }
      if (payload.type === "CHAT_MESSAGE") {
        setChat((cur) => [...cur, payload.message]);
        if (!chatOpen) setUnread((u) => u + 1);
      }
    };
    return () => ws.close();
  }, [chatOpen]);

  useEffect(() => {
    const timer = setInterval(() => { if (!demoMode) loadAll(chatOpen).catch(() => {}); }, 10000);
    return () => clearInterval(timer);
  }, [chatOpen, demoMode]);

  useEffect(() => {
    if (!demoMode) return undefined;
    const started = Date.now();
    setDemoHistory(
      Array.from({ length: 40 }).map((_, idx) => ({
        timestamp: new Date(started - (40 - idx) * 60000).toISOString(),
        fatigue_score: 28,
        load_score: 34,
      }))
    );
    setDemoVideoSummary({
      daily_total_min: 8,
      session_count: 1,
      by_platform_min: { youtube_shorts: 8, instagram_reels: 0, tiktok: 0 },
      escape_behavior_score: 18,
      insights: ["Demo mode uses simulated metadata to keep the flow alive."],
    });
    const timer = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - started) / 1000);
      const stage = Math.min(5, Math.floor(elapsedSec / 15));
      const fatigue = clamp(24 + stage * 12 + Math.sin(elapsedSec / 5) * 4, 20, 95);
      const load = clamp(30 + stage * 10 + Math.cos(elapsedSec / 7) * 5, 22, 95);
      const next = {
        ...state,
        timestamp: new Date().toISOString(),
        state_label: fatigue >= 80 ? "Burnout Risk" : fatigue >= 65 ? "Fatigued" : fatigue >= 40 ? "High Load" : "Normal",
        fatigue_score: Math.round(fatigue),
        load_score: Math.round(load),
        confidence: clamp(0.45 + stage * 0.1, 0.45, 0.95),
        model_maturity: clamp(0.25 + stage * 0.12, 0.25, 0.9),
        explanation: [
          { feature: "typing_speed", reason: stage >= 2 ? "typing speed dropped below your baseline rhythm" : "typing rhythm remains stable" },
          { feature: "fragmentation", reason: stage >= 3 ? "app switching increased in the current block" : "context switching is moderate" },
          { feature: "escape", reason: stage >= 4 ? "short-form usage spiked during focus hours" : "escape-behavior signal is low" },
        ],
      };
      setDemoState(next);
      setDemoHistory((current) => [...current.slice(-89), { timestamp: next.timestamp, fatigue_score: next.fatigue_score, load_score: next.load_score }]);
      setDemoVideoSummary((current) => ({
        ...(current || {}),
        daily_total_min: 8 + stage * 10,
        session_count: 1 + stage,
        by_platform_min: {
          youtube_shorts: 8 + stage * 6,
          instagram_reels: stage >= 2 ? stage * 4 : 0,
          tiktok: stage >= 4 ? stage * 3 : 0,
        },
        escape_behavior_score: clamp(18 + stage * 14, 18, 95),
      }));
    }, 2500);
    return () => clearInterval(timer);
  }, [demoMode, state]);

  useEffect(() => {
    if (!labStartedAt) return undefined;
    const t = setInterval(() => setLabTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [labStartedAt]);

  const viewState = demoMode ? (demoState || state) : state;
  const viewHistory = demoMode ? (demoHistory.length ? demoHistory : history) : history;
  const viewVideoSummary = demoMode ? (demoVideoSummary || videoSummary) : videoSummary;

  const appBreakdown = useMemo(() => {
    const map = new Map();
    telemetryPoints.forEach((p) => {
      const key = p.active_domain || p.app_name || "Unknown";
      if (!map.has(key)) map.set(key, { domain: key, active: 0, switches: 0, short: 0 });
      const row = map.get(key);
      row.active += Number(p.active_seconds || 0) / 60;
      row.switches += Number(p.tab_switches || 0);
      row.short += Number(p.short_video_seconds || 0) / 60;
    });
    return [...map.values()].sort((a, b) => b.active - a.active);
  }, [telemetryPoints]);

  const derived = useMemo(() => {
    const features = viewState?.current_features || {};
    const fatigue = Number(viewState?.fatigue_score || 0);
    const load = Number(viewState?.load_score || 0);
    const stress = clamp(load * 0.65 + Number(features.error_rate || 0) * 100 * 0.2 + Number(features.fragmentation_index || 0) * 6, 0, 100);
    const escape = clamp(Math.max(Number(viewVideoSummary?.escape_behavior_score || 0), Number(features.entertainment_ratio || 0) * 150), 0, 100);
    const focus = clamp(100 - (fatigue * 0.5 + load * 0.35 + escape * 0.2), 0, 100);
    return { fatigue, load, stress: Math.round(stress), escape: Math.round(escape), focus: Math.round(focus), confidence: Math.round(Number(viewState?.confidence || 0) * 100) };
  }, [viewState, viewVideoSummary]);

  const loadChart = useMemo(() => viewHistory.map((p) => ({
    t: new Date(p.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    load: Math.round(p.load_score || 0),
    fatigue: Math.round(p.fatigue_score || 0),
  })), [viewHistory]);

  const typingChart = useMemo(() => telemetryPoints.map((p) => ({
    t: new Date(p.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    speed: Math.round((Number(p.character_count || 0) / Math.max(Number(p.active_seconds || 60), 1)) * 60),
  })), [telemetryPoints]);

  const topReasons = (viewState?.explanation || []).slice(0, 3).map((r) => r.reason);
  const labElapsedMin = Math.max(0.05, labStartedAt ? (labTick - labStartedAt) / 60000 : 0.05);
  const labWpm = (labCharCount / 5) / labElapsedMin;
  const labAvgIki = mean(labLatencies);
  const labErr = labKeyCount ? labBackspaceCount / labKeyCount : 0;
  const labVar = std(labLatencies);
  const latencyBins = useMemo(() => {
    const buckets = [["0-100", 0, 100], ["100-200", 100, 200], ["200-350", 200, 350], ["350-600", 350, 600], ["600+", 600, Infinity]];
    return buckets.map(([name, lo, hi]) => ({ bucket: name, count: labLatencies.filter((v) => v >= lo && v < hi).length }));
  }, [labLatencies]);

  function handleTypingKeyDown(event) {
    if (!labStartedAt) setLabStartedAt(Date.now());
    const nowMs = Date.now();
    downMapRef.current[event.code] = nowMs;
    setLabKeyCount((v) => v + 1);
    if (event.key.length === 1) setLabCharCount((v) => v + 1);
    if (event.key === "Backspace") setLabBackspaceCount((v) => v + 1);
    if (lastKeyDownRef.current !== null) {
      const delta = nowMs - lastKeyDownRef.current;
      if (delta < 3000) setLabLatencies((arr) => [...arr.slice(-399), delta]);
    }
    lastKeyDownRef.current = nowMs;
  }

  function handleTypingKeyUp(event) {
    const downAt = downMapRef.current[event.code];
    if (downAt !== undefined) {
      const hold = Date.now() - downAt;
      if (hold > 0 && hold < 1500) setLabHolds((arr) => [...arr.slice(-399), hold]);
      delete downMapRef.current[event.code];
    }
  }

  async function sendChatText() {
    if (!chatInput.trim()) return;
    const body = { text: chatInput.trim() };
    setChatInput("");
    const res = await fetch(`${API_BASE}/chat/message?user_id=${USER_ID}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json()).catch(() => null);
    if (res?.assistant_messages?.length || res?.user_message) await loadAll(chatOpen);
  }

  async function sendQuickReply(action, payload) {
    await fetch(`${API_BASE}/chat/message?user_id=${USER_ID}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quick_reply_action: action, quick_reply_payload: payload || {} }) }).catch(() => {});
    await loadAll(chatOpen);
  }

  async function logVideoSession(event) {
    event.preventDefault();
    await fetch(`${API_BASE}/video-sessions?user_id=${USER_ID}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(videoForm) }).catch(() => {});
    setVideoForm((v) => ({ ...v, duration_min: 6, note: "" }));
    await loadAll(chatOpen);
  }

  async function submitEMA() {
    await fetch(`${API_BASE}/self-reports?user_id=${USER_ID}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ report_type: "check_in", fatigue_level: ema.fatigue, stress_level: ema.stress, answer_values: { focus_last_hour: ema.focus } }) }).catch(() => {});
    await loadAll(chatOpen);
  }

  async function saveProfile(event) {
    event.preventDefault();
    setSavingProfile(true);
    await fetch(`${API_BASE}/profile/onboarding?user_id=${USER_ID}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...profile, onboarding_complete: true }) }).catch(() => {});
    setSavingProfile(false);
    await loadAll(chatOpen);
  }

  useEffect(() => {
    if (!labStartedAt || labKeyCount < 8) return undefined;
    const timer = setInterval(async () => {
      const payload = {
        model_maturity: Number(state?.model_maturity || 0.25),
        typing_speed_cpm: clamp(Math.round((labCharCount / labElapsedMin) || 0), 0, 500),
        error_rate: clamp(labErr, 0, 1),
        mean_interkey_latency: clamp(labAvgIki, 0, 2000),
        std_interkey_latency: clamp(labVar, 0, 2000),
        current_session_length_min: clamp(Number(state?.current_features?.current_session_length_min || labElapsedMin), 0, 600),
      };
      const res = await fetch(`${API_BASE}/ml/predict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then((r) => r.json()).catch(() => null);
      if (res) setLabPrediction(res);
    }, 7000);
    return () => clearInterval(timer);
  }, [labStartedAt, labKeyCount, labCharCount, labElapsedMin, labErr, labAvgIki, labVar, state]);

  const rootGreeting = `${new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"}`;

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="brand">
          <Sparkles size={17} />
          <div>
            <strong>NeuroLens AI</strong>
            <span>Calm intelligence</span>
          </div>
        </div>
        <nav>
          {VIEWS.map((v) => (
            <button key={v.id} className={`nav-btn ${activeView === v.id ? "active" : ""}`} onClick={() => setActiveView(v.id)}>
              <v.icon size={15} />
              <span>{v.label}</span>
            </button>
          ))}
        </nav>
        <div className="nav-controls">
          <button className="ghost" onClick={() => setDemoMode((m) => !m)}>{demoMode ? "Exit demo mode" : "Hackathon demo mode"}</button>
          <button className="ghost" onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{rootGreeting}</p>
            <h1>Session awareness without content surveillance</h1>
            <p className="subtle">Current state confidence: <strong>{derived.confidence}%</strong></p>
          </div>
          <div className="state-pill" style={{ borderColor: stateColor(viewState?.state_label || "Normal") }}>
            <span>State</span>
            <strong style={{ color: stateColor(viewState?.state_label || "Normal") }}>{viewState?.state_label || "Normal"}</strong>
          </div>
        </header>

        {activeView === "dashboard" && (
          <section className="view-grid">
            <div className="panel metric-row">
              <div className="metric-card"><span>Fatigue</span><strong>{Math.round(derived.fatigue)}/100</strong></div>
              <div className="metric-card"><span>Stress index</span><strong>{derived.stress}/100</strong></div>
              <div className="metric-card"><span>Focus quality</span><strong>{derived.focus}/100</strong></div>
              <div className="metric-card"><span>Escape behavior</span><strong>{derived.escape}/100</strong></div>
              <div className="metric-card"><span>Model confidence</span><strong>{derived.confidence}%</strong></div>
            </div>

            <div className="panel ring-panel">
              <div className="panel-head"><h2>Current score</h2><p>Top explainers</p></div>
              <ScoreRing value={Math.max(derived.fatigue, derived.load)} label={viewState?.state_label || "Normal"} />
              <div className="driver-list">
                {topReasons.length ? topReasons.map((r) => <p key={r}>- {r}.</p>) : <p>Still learning your rhythm.</p>}
              </div>
            </div>

            <div className="panel chart-panel">
              <div className="panel-head"><h2>Cognitive load line</h2><p>Last 90 minutes</p></div>
              <ResponsiveContainer width="100%" height={230}>
                <AreaChart data={loadChart}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="t" stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="load" stroke="#84ac9c" fill="#84ac9c44" />
                  <Line type="monotone" dataKey="fatigue" stroke="#caa275" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="panel chart-panel">
              <div className="panel-head"><h2>Typing speed</h2><p>Telemetry-derived trend</p></div>
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={typingChart}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="t" stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="speed" stroke="#93b4cc" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="panel table-panel">
              <div className="panel-head"><h2>Current app activity table</h2><p>Metadata only</p></div>
              <table>
                <thead><tr><th>Domain</th><th>Active min</th><th>Switches</th><th>Short video min</th></tr></thead>
                <tbody>
                  {appBreakdown.slice(0, 8).map((r) => <tr key={r.domain}><td>{r.domain}</td><td>{r.active.toFixed(1)}</td><td>{r.switches}</td><td>{r.short.toFixed(1)}</td></tr>)}
                  {!appBreakdown.length && <tr><td colSpan={4}>No telemetry rows yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "typing" && (
          <section className="view-grid">
            <div className="panel typing-panel">
              <div className="panel-head"><h2>Live keystroke analysis</h2><p>Timing rhythm only, never typed content</p></div>
              <textarea className="typing-box" value={labText} onChange={(e) => setLabText(e.target.value)} onKeyDown={handleTypingKeyDown} onKeyUp={handleTypingKeyUp} placeholder="Type naturally for live metrics..." />
              <div className="metric-row compact">
                <div className="metric-card"><span>WPM</span><strong>{Math.round(labWpm)}</strong></div>
                <div className="metric-card"><span>Inter-key</span><strong>{Math.round(labAvgIki)} ms</strong></div>
                <div className="metric-card"><span>Error rate</span><strong>{Math.round(labErr * 100)}%</strong></div>
                <div className="metric-card"><span>Variability</span><strong>{Math.round(labVar)} ms</strong></div>
              </div>
              <div className="prediction-chip">{labPrediction ? `Live model -> Fatigue ${Math.round(labPrediction.fatigue_score || 0)} | Load ${Math.round(labPrediction.load_score || 0)}` : "Model prediction updates while typing."}</div>
            </div>
            <div className="panel chart-panel">
              <div className="panel-head"><h2>Inter-key histogram</h2><p>Distribution of latency buckets</p></div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={latencyBins}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="bucket" stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#94b2c8" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "video" && (
          <section className="view-grid">
            <form className="panel video-form" onSubmit={logVideoSession}>
              <div className="panel-head"><h2>Video tracker / escape behavior</h2><p>Manual logger now, extension-ready for auto metadata</p></div>
              <div className="form-grid">
                <label><span>Platform</span><select value={videoForm.platform} onChange={(e) => setVideoForm((v) => ({ ...v, platform: e.target.value }))}><option value="youtube_shorts">YouTube Shorts</option><option value="instagram_reels">Instagram Reels</option><option value="tiktok">TikTok</option></select></label>
                <label><span>Duration (min)</span><input type="number" min="1" max="240" value={videoForm.duration_min} onChange={(e) => setVideoForm((v) => ({ ...v, duration_min: Number(e.target.value || 0) }))} /></label>
                <label className="wide"><span>Note</span><input value={videoForm.note} onChange={(e) => setVideoForm((v) => ({ ...v, note: e.target.value }))} placeholder="Optional context" /></label>
                <label className="checkbox"><input type="checkbox" checked={videoForm.in_focus_block} onChange={(e) => setVideoForm((v) => ({ ...v, in_focus_block: e.target.checked }))} /><span>During expected focus window</span></label>
              </div>
              <button className="primary" type="submit">Log session</button>
            </form>
            <div className="panel ring-panel">
              <div className="panel-head"><h2>Escape behavior score</h2><p>Behavioral disengagement proxy</p></div>
              <ScoreRing value={viewVideoSummary?.escape_behavior_score || 0} label="Metadata proxy" />
              <div className="driver-list">{(viewVideoSummary?.insights || []).map((i) => <p key={i}>- {i}</p>)}</div>
            </div>
            <div className="panel chart-panel">
              <div className="panel-head"><h2>Per-platform totals</h2><p>Today</p></div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={Object.entries(viewVideoSummary?.by_platform_min || {}).map(([k, v]) => ({ platform: PLATFORM_LABELS[k] || k, minutes: v }))}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="platform" stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="minutes">{[0, 1, 2].map((i) => <Cell key={i} fill={["#95afcb", "#89ad90", "#caa177"][i]} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="panel table-panel">
              <div className="panel-head"><h2>Recent logged sessions</h2><p>{Math.round(Number(viewVideoSummary?.daily_total_min || 0))} min today</p></div>
              <table>
                <thead><tr><th>Time</th><th>Platform</th><th>Duration</th><th>Focus block</th></tr></thead>
                <tbody>
                  {videoSessions.slice(0, 10).map((s) => <tr key={s.id}><td>{new Date(s.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td><td>{PLATFORM_LABELS[s.platform] || s.platform}</td><td>{Math.round(s.duration_min)} min</td><td>{s.in_focus_block ? "Yes" : "No"}</td></tr>)}
                  {!videoSessions.length && <tr><td colSpan={4}>No sessions logged yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "alerts" && (
          <section className="view-grid">
            <div className="panel">
              <div className="panel-head"><h2>Alerts & interventions</h2><p>Supportive, non-clinical guidance</p></div>
              <div className="alert-stack">
                <article className="alert-card medium">
                  <h3>High fatigue detected</h3>
                  <p><strong>Why:</strong> Fatigue score and latency trends are rising together.</p>
                  <p><strong>Action:</strong> Take a 3-minute microbreak and restart with one small task.</p>
                </article>
                <article className="alert-card medium">
                  <h3>45+ minute focus streak</h3>
                  <p><strong>Why:</strong> Session duration crossed a common strain threshold.</p>
                  <p><strong>Action:</strong> Quick reset: breathe, stretch, hydrate.</p>
                </article>
                <article className="alert-card medium">
                  <h3>Task-switching spike</h3>
                  <p><strong>Why:</strong> Fragmentation index is above your normal rhythm.</p>
                  <p><strong>Action:</strong> Run one 15-minute focus block with fewer app hops.</p>
                </article>
              </div>
            </div>
            <div className="panel">
              <div className="panel-head"><h2>Recent model nudges</h2><p>Direct from backend</p></div>
              <div className="alert-stack">
                {notifications.map((n) => (
                  <article key={`${n.created_at}-${n.title}`} className={`alert-card ${n.severity || "medium"}`}>
                    <h3>{n.title}</h3>
                    <p>{n.body}</p>
                    <small>{new Date(n.created_at).toLocaleString()}</small>
                  </article>
                ))}
                {!notifications.length && <p className="muted">No nudges yet.</p>}
              </div>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "activity" && (
          <section className="view-grid">
            <div className="panel chart-panel">
              <div className="panel-head"><h2>Activity category split</h2><p>Current 5-minute window</p></div>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={[
                      { name: "Focus", value: Number(viewState?.current_features?.seconds_in_focus_apps || 0) },
                      { name: "Communication", value: Number(viewState?.current_features?.seconds_in_communication_apps || 0) },
                      { name: "Entertainment", value: Number(viewState?.current_features?.seconds_in_entertainment_apps || 0) },
                    ]}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={90}
                  >
                    <Cell fill="#88ad97" />
                    <Cell fill="#91b2c8" />
                    <Cell fill="#c8a175" />
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="panel table-panel">
              <div className="panel-head"><h2>App breakdown</h2><p>Recent telemetry</p></div>
              <table>
                <thead><tr><th>Domain</th><th>Active min</th><th>Switches</th><th>Short video min</th></tr></thead>
                <tbody>
                  {appBreakdown.map((r) => <tr key={r.domain}><td>{r.domain}</td><td>{r.active.toFixed(1)}</td><td>{r.switches}</td><td>{r.short.toFixed(1)}</td></tr>)}
                  {!appBreakdown.length && <tr><td colSpan={4}>No telemetry rows yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "onboarding" && (
          <section className="view-grid">
            <form className="panel onboarding-panel" onSubmit={saveProfile}>
              <div className="panel-head"><h2>Onboarding + EMA calibration</h2><p>4 lightweight screens</p></div>
              <div className="stepper">
                {[1, 2, 3, 4].map((s) => <button key={s} type="button" className={`step ${onboardingStep === s ? "active" : ""}`} onClick={() => setOnboardingStep(s)}>Step {s}</button>)}
              </div>
              {onboardingStep === 1 && (
                <div className="form-grid">
                  <label><span>Current fatigue</span><input type="range" min="0" max="100" value={profile.current_fatigue} onChange={(e) => setProfile((p) => ({ ...p, current_fatigue: Number(e.target.value) }))} /></label>
                  <label><span>Current stress</span><input type="range" min="0" max="100" value={profile.current_stress} onChange={(e) => setProfile((p) => ({ ...p, current_stress: Number(e.target.value) }))} /></label>
                </div>
              )}
              {onboardingStep === 2 && (
                <div className="form-grid">
                  <label><span>Focus duration (min)</span><input type="number" min="15" max="240" value={profile.focus_capacity_minutes} onChange={(e) => setProfile((p) => ({ ...p, focus_capacity_minutes: Number(e.target.value) }))} /></label>
                  <label><span>Work style</span><select value={profile.break_style} onChange={(e) => setProfile((p) => ({ ...p, break_style: e.target.value }))}><option value="short_sprints">Short sprints</option><option value="balanced">Balanced</option><option value="long_focus">Long blocks</option></select></label>
                </div>
              )}
              {onboardingStep === 3 && (
                <div className="form-grid">
                  <label><span>Break habit</span><select value={profile.preferred_break_habit} onChange={(e) => setProfile((p) => ({ ...p, preferred_break_habit: e.target.value }))}><option value="rare_breaks">Rare breaks</option><option value="balanced">Balanced</option><option value="frequent_breaks">Frequent breaks</option></select></label>
                  <label><span>Short video effect</span><select value={profile.video_use_effect} onChange={(e) => setProfile((p) => ({ ...p, video_use_effect: e.target.value }))}><option value="refreshing">Refreshing</option><option value="distracting">Distracting</option><option value="mixed">Mixed</option></select></label>
                  <label className="wide"><span>Productivity goal</span><input value={profile.productivity_goal} onChange={(e) => setProfile((p) => ({ ...p, productivity_goal: e.target.value }))} placeholder="Optional goal" /></label>
                </div>
              )}
              {onboardingStep === 4 && (
                <div className="form-grid">
                  <label className="wide"><span>Focus apps</span><textarea value={profile.focus_apps} onChange={(e) => setProfile((p) => ({ ...p, focus_apps: e.target.value }))} /></label>
                  <label className="wide"><span>Distraction apps</span><textarea value={profile.distraction_apps} onChange={(e) => setProfile((p) => ({ ...p, distraction_apps: e.target.value }))} /></label>
                </div>
              )}
              <div className="typing-actions">
                <button type="button" className="ghost" onClick={() => setOnboardingStep((s) => clamp(s - 1, 1, 4))}>Previous</button>
                <button type="button" className="ghost" onClick={() => setOnboardingStep((s) => clamp(s + 1, 1, 4))}>Next</button>
                <button type="submit" className="primary">{savingProfile ? "Saving..." : "Save profile"}</button>
              </div>
            </form>
            <div className="panel">
              <div className="panel-head"><h2>EMA check-in</h2><p>Fast calibration loop</p></div>
              <div className="form-grid">
                <label><span>Fatigue now (0-10)</span><input type="range" min="0" max="10" value={ema.fatigue} onChange={(e) => setEma((v) => ({ ...v, fatigue: Number(e.target.value) }))} /></label>
                <label><span>Stress now (0-10)</span><input type="range" min="0" max="10" value={ema.stress} onChange={(e) => setEma((v) => ({ ...v, stress: Number(e.target.value) }))} /></label>
                <label className="wide"><span>Focus in last hour (0-10)</span><input type="range" min="0" max="10" value={ema.focus} onChange={(e) => setEma((v) => ({ ...v, focus: Number(e.target.value) }))} /></label>
              </div>
              <button className="primary" onClick={submitEMA}>Submit check-in</button>
              <div className="driver-list"><p>Calibration labels: {calibration?.label_count || 0}</p></div>
            </div>
            <TrustLine />
          </section>
        )}

        {activeView === "explainability" && (
          <section className="view-grid">
            <div className="panel">
              <div className="panel-head"><h2>Explainability</h2><p>Why the model said this</p></div>
              <div className="driver-list">
                {(viewState?.explanation || []).map((e, i) => <p key={`${e.feature}-${i}`}><strong>{i + 1}.</strong> {e.reason}</p>)}
                {!(viewState?.explanation || []).length && <p>No explanation rows yet.</p>}
              </div>
              <div className="metric-row compact">
                <div className="metric-card"><span>Confidence</span><strong>{derived.confidence}%</strong></div>
                <div className="metric-card"><span>Maturity</span><strong>{Math.round(Number(viewState?.model_maturity || 0) * 100)}%</strong></div>
                <div className="metric-card"><span>Normal cutoff</span><strong>{Math.round(calibration?.thresholds?.normal_max || 40)}</strong></div>
                <div className="metric-card"><span>Fatigue cutoff</span><strong>{Math.round(calibration?.thresholds?.fatigued_max || 80)}</strong></div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-head"><h2>Judge-ready trust points</h2><p>No black-box claims</p></div>
              <ul className="judge-list">
                <li>Model output is paired with behavior-level explanations.</li>
                <li>Thresholds are personalized with user check-ins.</li>
                <li>Escape behavior uses metadata proxy, never content analysis.</li>
                <li>Confidence is shown explicitly for transparency.</li>
              </ul>
            </div>
            <TrustLine />
          </section>
        )}
      </main>

      <ChatWidget
        open={chatOpen}
        unread={unread}
        messages={chat}
        onToggle={() => {
          const next = !chatOpen;
          setChatOpen(next);
          if (next) {
            setUnread(0);
            fetch(`${API_BASE}/chat/thread?user_id=${USER_ID}&mark_read=true`).catch(() => {});
          }
        }}
        onSend={sendChatText}
        onQuickReply={sendQuickReply}
        input={chatInput}
        setInput={setChatInput}
      />
    </div>
  );
}
