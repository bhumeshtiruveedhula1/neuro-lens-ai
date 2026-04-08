import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

const API_BASE = "http://localhost:8001";
const USER_ID = "default";
const WS_URL = `ws://localhost:8001/ws/live?user_id=${USER_ID}`;

const defaultProfile = {
  baseline_fatigue_week: 35,
  baseline_stress_week: 35,
  current_fatigue: 30,
  current_stress: 30,
  deep_focus_capacity_min: 75,
  preferred_work_cycle_min: 50,
  focus_capacity_minutes: 75,
  break_style: "balanced",
  user_target_hours: 6,
  context_switch_sensitivity: 50,
  avg_sleep_hours: 7.5,
  last_night_sleep_hours: 7,
  workday_start_hour: 9,
  workday_end_hour: 18,
  learning_period_days: 7,
  alerts_enabled: true,
  focus_apps: "",
  distraction_apps: "",
  communication_apps: "",
  entertainment_apps: "",
  onboarding_complete: false,
};

function stateColor(label) {
  if (label === "Burnout Risk") return "#f97373";
  if (label === "Fatigued") return "#f6a14a";
  if (label === "High Load") return "#e8d47a";
  return "#7cd89a";
}

function reasonText(label) {
  if (label === "Burnout Risk") return "You look pretty drained right now.";
  if (label === "Fatigued") return "You may be getting tired.";
  if (label === "High Load") return "Your brain is working hard.";
  return "You are in a normal range.";
}

function Gauge({ fatigue, load, label }) {
  const score = Math.round(Math.max(fatigue || 0, load || 0));
  const color = stateColor(label);
  return (
    <div className="gauge-wrap">
      <div className="gauge-track">
        <div className="gauge-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <div className="gauge-meta">
        <strong>{score}/100</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function metricMinutes(value) {
  return Math.round(Number(value || 0));
}

function ChatWidget({
  open,
  unread,
  messages,
  onToggle,
  onSend,
  onQuickReply,
  input,
  setInput,
}) {
  return (
    <div className={`chat-shell ${open ? "open" : ""}`}>
      <button className="chat-fab" onClick={onToggle}>
        <span>Companion Chat</span>
        {unread > 0 && <b>{unread}</b>}
      </button>
      {open && (
        <div className="chat-panel">
          <div className="chat-head">
            <strong>NeuroLens Companion</strong>
            <span>Warm check-ins, simple nudges</span>
          </div>
          <div className="chat-body">
            {messages.map((message) => (
              <div key={message.id} className={`bubble ${message.role}`}>
                <p>{message.text}</p>
                {message.quick_replies?.length > 0 && (
                  <div className="quick-row">
                    {message.quick_replies.map((reply) => (
                      <button
                        key={reply.id}
                        className="quick-btn"
                        onClick={() => onQuickReply(reply.action, reply.payload || {})}
                      >
                        {reply.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <form
            className="chat-input-row"
            onSubmit={(event) => {
              event.preventDefault();
              onSend();
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Type how you are feeling..."
            />
            <button type="submit">Send</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState([]);
  const [profile, setProfile] = useState(defaultProfile);
  const [notifications, setNotifications] = useState([]);
  const [calibration, setCalibration] = useState(null);
  const [chat, setChat] = useState([]);
  const [unread, setUnread] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatAutoOpened, setChatAutoOpened] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadAll(markRead = false) {
    const [
      profileRes,
      latestStateRes,
      historyRes,
      notificationsRes,
      calibrationRes,
      chatRes,
    ] = await Promise.all([
      fetch(`${API_BASE}/profile/onboarding?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API_BASE}/state/latest?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API_BASE}/metrics/history?user_id=${USER_ID}&limit=90`).then((r) => r.json()),
      fetch(`${API_BASE}/notifications?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API_BASE}/calibration/status?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API_BASE}/chat/thread?user_id=${USER_ID}&mark_read=${markRead ? "true" : "false"}`).then((r) => r.json()),
    ]);

    setProfile({
      ...profileRes.profile,
      focus_apps: (profileRes.profile.focus_apps || []).join(", "),
      distraction_apps: (profileRes.profile.distraction_apps || []).join(", "),
      communication_apps: (profileRes.profile.communication_apps || []).join(", "),
      entertainment_apps: (profileRes.profile.entertainment_apps || []).join(", "),
    });
    setState(latestStateRes);
    setHistory(historyRes.points || []);
    setNotifications(notificationsRes.notifications || []);
    setCalibration(calibrationRes);
    setChat(chatRes.messages || []);
    setUnread(chatRes.unread_count || 0);
  }

  useEffect(() => {
    loadAll().catch(console.error);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => ws.send("ready");
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "LIVE_STATE") {
        setState(payload);
        setHistory((current) =>
          [
            ...current.slice(-89),
            {
              timestamp: payload.timestamp,
              fatigue_score: payload.fatigue_score,
              load_score: payload.load_score,
              confidence: payload.confidence,
              state_label: payload.state_label,
            },
          ]
        );
      }
      if (payload.type === "CHAT_MESSAGE") {
        setChat((current) => [...current, payload.message]);
        if (!chatOpen) setUnread((value) => value + 1);
      }
    };
    return () => ws.close();
  }, [chatOpen]);

  useEffect(() => {
    const timer = setInterval(() => {
      loadAll(chatOpen).catch(() => {});
    }, 12000);
    return () => clearInterval(timer);
  }, [chatOpen]);

  useEffect(() => {
    if (!chatAutoOpened && unread > 0) {
      setChatOpen(true);
      setChatAutoOpened(true);
    }
  }, [unread, chatAutoOpened]);

  const chartData = useMemo(
    () =>
      history.map((point) => ({
        t: new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        fatigue: point.fatigue_score,
        load: point.load_score,
      })),
    [history]
  );

  const reasons = (state?.explanation || []).slice(0, 3).map((item) => item.reason);
  const plain = state?.plain_summary || reasonText(state?.state_label || "Normal");
  const today = state?.today_summary || { deep_focus_minutes: 0, high_fatigue_minutes: 0, breaks_taken: 0 };

  async function saveProfile(event) {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...profile,
      focus_apps: profile.focus_apps,
      distraction_apps: profile.distraction_apps,
      communication_apps: profile.communication_apps,
      entertainment_apps: profile.entertainment_apps,
    };
    await fetch(`${API_BASE}/profile/onboarding?user_id=${USER_ID}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSaving(false);
    await loadAll(chatOpen);
  }

  async function sendChatText() {
    if (!chatInput.trim()) return;
    const text = chatInput;
    setChatInput("");
    const response = await fetch(`${API_BASE}/chat/message?user_id=${USER_ID}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => r.json());
    const next = [];
    if (response.user_message) next.push(response.user_message);
    if (response.assistant_messages?.length) next.push(...response.assistant_messages);
    if (next.length) setChat((current) => [...current, ...next]);
    await loadAll(chatOpen);
  }

  async function sendQuickReply(action, payload) {
    const response = await fetch(`${API_BASE}/chat/message?user_id=${USER_ID}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quick_reply_action: action, quick_reply_payload: payload || {} }),
    }).then((r) => r.json());
    const next = [];
    if (response.user_message) next.push(response.user_message);
    if (response.assistant_messages?.length) next.push(...response.assistant_messages);
    if (next.length) setChat((current) => [...current, ...next]);
    await loadAll(chatOpen);
  }

  function toggleChat() {
    const next = !chatOpen;
    setChatOpen(next);
    if (next) {
      setUnread(0);
      fetch(`${API_BASE}/chat/thread?user_id=${USER_ID}&mark_read=true`).catch(() => {});
    }
  }

  return (
    <div className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">A supportive first-week companion</p>
          <h1>NeuroLens AI</h1>
          <p className="lede">
            I watch how you work in the background, and I try to tell when your brain is getting tired or overloaded, so you can take care of yourself.
          </p>
        </div>
        <div className="hero-state" style={{ borderColor: stateColor(state?.state_label || "Normal") }}>
          <span>Current state</span>
          <strong style={{ color: stateColor(state?.state_label || "Normal") }}>{state?.state_label || "Normal"}</strong>
          <small>{plain}</small>
        </div>
      </section>

      <section className="grid">
        <div className="panel live-panel">
          <div className="panel-head">
            <h2>Live score</h2>
            <p>Updated each minute</p>
          </div>
          <Gauge fatigue={state?.fatigue_score} load={state?.load_score} label={state?.state_label || "Normal"} />
          <div className="metric-grid">
            <div className="metric-card"><span>Fatigue</span><strong>{Math.round(state?.fatigue_score || 0)}</strong></div>
            <div className="metric-card"><span>Load</span><strong>{Math.round(state?.load_score || 0)}</strong></div>
            <div className="metric-card"><span>Confidence</span><strong>{Math.round((state?.confidence || 0) * 100)}%</strong></div>
            <div className="metric-card"><span>Maturity</span><strong>{Math.round((state?.model_maturity || 0) * 100)}%</strong></div>
          </div>
          <div className="insight-block">
            <h3>Why?</h3>
            {reasons.length === 0 && <p>Still learning your pattern.</p>}
            {reasons.map((text) => (
              <p key={text}>- {text.charAt(0).toUpperCase() + text.slice(1)}.</p>
            ))}
          </div>
        </div>

        <div className="panel history-panel">
          <div className="panel-head">
            <h2>Last 90 minutes</h2>
            <p>Fatigue and load trend</p>
          </div>
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="fatigueFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#f6a14a" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#f6a14a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="t" stroke="rgba(255,255,255,0.4)" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} stroke="rgba(255,255,255,0.4)" tickLine={false} axisLine={false} />
              <Tooltip />
              <Area type="monotone" dataKey="fatigue" stroke="#f6a14a" fill="url(#fatigueFill)" />
              <Line type="monotone" dataKey="load" stroke="#e8d47a" dot={false} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel burnout-panel">
          <div className="panel-head">
            <h2>Today</h2>
            <p>Your gentle daily snapshot</p>
          </div>
          <div className="today-grid">
            <div><strong>{metricMinutes(today.deep_focus_minutes)} min</strong><span>Deep focus</span></div>
            <div><strong>{metricMinutes(today.high_fatigue_minutes)} min</strong><span>High fatigue</span></div>
            <div><strong>{metricMinutes(today.breaks_taken)}</strong><span>Breaks</span></div>
          </div>
          <div className="insight-block">
            <h3>Personalized cutoff</h3>
            <p>{calibration?.thresholds?.reason || "Using first-week defaults while I learn."}</p>
            <p>Normal {"<="} {Math.round(calibration?.thresholds?.normal_max || 40)}, High Load {"<="} {Math.round(calibration?.thresholds?.high_load_max || 65)}</p>
          </div>
        </div>

        <form className="panel onboarding-panel" onSubmit={saveProfile}>
          <div className="panel-head">
            <h2>First-week setup</h2>
            <p>Quick answers help me personalize sooner</p>
          </div>
          <div className="form-grid">
            <label>
              <span>How long can you focus before a break?</span>
              <input
                type="number"
                min="15"
                max="240"
                value={profile.focus_capacity_minutes}
                onChange={(e) => setProfile((c) => ({ ...c, focus_capacity_minutes: Number(e.target.value) }))}
              />
            </label>
            <label>
              <span>How many good work hours do you aim for daily?</span>
              <input
                type="number"
                min="1"
                max="16"
                step="0.5"
                value={profile.user_target_hours}
                onChange={(e) => setProfile((c) => ({ ...c, user_target_hours: Number(e.target.value) }))}
              />
            </label>
            <label>
              <span>Break style</span>
              <select
                value={profile.break_style}
                onChange={(e) => setProfile((c) => ({ ...c, break_style: e.target.value }))}
              >
                <option value="short_sprints">Short sprints with many breaks</option>
                <option value="balanced">Balanced mix</option>
                <option value="long_focus">Long deep-focus blocks</option>
              </select>
            </label>
            <label>
              <span>How mentally tired are you this week? (0-100)</span>
              <input
                type="range"
                min="0"
                max="100"
                value={profile.baseline_fatigue_week}
                onChange={(e) => setProfile((c) => ({ ...c, baseline_fatigue_week: Number(e.target.value) }))}
              />
            </label>
            <label className="wide">
              <span>Focus apps (comma separated)</span>
              <textarea
                value={profile.focus_apps}
                onChange={(e) => setProfile((c) => ({ ...c, focus_apps: e.target.value }))}
              />
            </label>
            <label className="wide">
              <span>Distraction apps (comma separated)</span>
              <textarea
                value={profile.distraction_apps}
                onChange={(e) => setProfile((c) => ({ ...c, distraction_apps: e.target.value }))}
              />
            </label>
          </div>
          <button className="save-button" disabled={saving}>
            {saving ? "Saving..." : "Save first-week settings"}
          </button>
        </form>

        <div className="panel notifications-panel">
          <div className="panel-head">
            <h2>Recent nudges</h2>
            <p>Supportive, not pushy</p>
          </div>
          <div className="notification-list">
            {notifications.length === 0 && <p>No nudges yet.</p>}
            {notifications.map((item) => (
              <div key={`${item.created_at}-${item.title}`} className={`notification ${item.severity}`}>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
                <span>{new Date(item.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <ChatWidget
        open={chatOpen}
        unread={unread}
        messages={chat}
        onToggle={toggleChat}
        onSend={sendChatText}
        onQuickReply={sendQuickReply}
        input={chatInput}
        setInput={setChatInput}
      />
    </div>
  );
}
