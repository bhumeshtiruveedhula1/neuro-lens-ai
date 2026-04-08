"use strict";

const DASHBOARD_URL = "http://localhost:5173";
const RING_CIRCUMFERENCE = 2 * Math.PI * 35;

const scoreNum = document.getElementById("scoreNum");
const levelBadge = document.getElementById("levelBadge");
const coachMsg = document.getElementById("coachMsg");
const ringFill = document.getElementById("ringFill");
const mSpeed = document.getElementById("mSpeed");
const mError = document.getElementById("mError");
const mLatency = document.getElementById("mLatency");
const mTabs = document.getElementById("mTabs");
const lastUpdated = document.getElementById("lastUpdated");
const offlineNote = document.getElementById("offlineNote");
const noData = document.getElementById("noData");
const sparkCanvas = document.getElementById("sparkline");
const statusDot = document.getElementById("statusDot");
const chatSummary = document.getElementById("chatSummary");
const chatQuickRow = document.getElementById("chatQuickRow");

const LEVEL_COLORS = {
  "Normal": "#22c55e",
  "High Load": "#f59e0b",
  "Fatigued": "#fb923c",
  "Burnout Risk": "#ef4444",
};

function render(data) {
  const liveState = data?.state;
  if (!liveState) {
    coachMsg.textContent = "No live prediction yet. Generate data from the dashboard + extension.";
    return;
  }

  const severity = Math.round(Math.max(liveState.fatigue_score || 0, liveState.load_score || 0));
  const color = LEVEL_COLORS[liveState.state_label] || "#6b7280";
  const offset = RING_CIRCUMFERENCE * (1 - severity / 100);
  ringFill.style.strokeDashoffset = offset;
  ringFill.style.stroke = color;
  scoreNum.textContent = severity;
  scoreNum.style.color = color;
  levelBadge.textContent = liveState.state_label;
  levelBadge.style.background = `${color}22`;
  levelBadge.style.color = color;
  statusDot.style.background = color;

  coachMsg.textContent = (liveState.insights || [])[0] || "Monitoring your current pattern.";
  mSpeed.innerHTML = `${Math.round(liveState.current_features?.typing_speed_cpm || 0)}<span class="metric-unit">cpm</span>`;
  mError.innerHTML = `${Math.round((liveState.current_features?.error_rate || 0) * 100)}<span class="metric-unit">%</span>`;
  mLatency.innerHTML = `${Math.round(liveState.current_features?.mean_interkey_latency || 0)}<span class="metric-unit">ms</span>`;
  mTabs.textContent = Math.round(liveState.current_features?.tab_switches_per_min || 0);
  lastUpdated.textContent = new Date(liveState.timestamp).toLocaleTimeString();
  offlineNote.classList.toggle("visible", data.queueSize > 0);

  const history = liveState.history_minutes || [];
  if (history.length > 1) {
    noData.style.display = "none";
    drawSparkline(history);
  }

  renderChat(data?.chatMessages || [], data?.chatUnreadCount || 0);
}

function renderChat(messages, unreadCount) {
  const assistant = [...messages].reverse().find((m) => m.role === "assistant");
  if (!assistant) {
    chatSummary.textContent = "Your companion messages will appear here.";
    chatQuickRow.style.display = "none";
    chatQuickRow.innerHTML = "";
    return;
  }

  const unreadHint = unreadCount > 0 ? ` (${unreadCount} new)` : "";
  chatSummary.textContent = `${assistant.text}${unreadHint}`;
  chatQuickRow.innerHTML = "";

  const quick = assistant.quick_replies || [];
  if (!quick.length) {
    chatQuickRow.style.display = "none";
    return;
  }

  chatQuickRow.style.display = "flex";
  quick.slice(0, 3).forEach((reply) => {
    const button = document.createElement("button");
    button.className = "btn";
    button.style.flex = "unset";
    button.style.padding = "6px 9px";
    button.style.fontSize = "9px";
    button.textContent = reply.label;
    button.onclick = () => sendQuickReply(reply.action, reply.payload || {});
    chatQuickRow.appendChild(button);
  });
}

function sendQuickReply(action, payload) {
  chrome.runtime.sendMessage(
    { type: "CHAT_REPLY", action, payload },
    () => poll()
  );
}

function drawSparkline(history) {
  const canvas = sparkCanvas;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.offsetWidth;
  const height = canvas.offsetHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const scores = history.map((point) => Math.max(point.load_score || 0, point.fatigue_score || 0));
  const step = width / Math.max(scores.length - 1, 1);
  ctx.beginPath();
  ctx.moveTo(0, height - (scores[0] / 100) * height);
  scores.forEach((score, index) => {
    const x = index * step;
    const y = height - (score / 100) * height;
    ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function poll() {
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
    if (chrome.runtime.lastError) return;
    render(response);
  });
}

poll();
const poller = setInterval(poll, 5000);
window.addEventListener("unload", () => clearInterval(poller));

chrome.runtime.sendMessage({ type: "CHAT_MARK_READ" }, () => {});

document.getElementById("btnDashboard").addEventListener("click", () => {
  chrome.tabs.create({ url: DASHBOARD_URL });
});

document.getElementById("btnReset").addEventListener("click", () => {
  chrome.storage.local.clear(() => window.close());
});
