"use strict";

const CONFIG = {
  USER_ID: "default",
  BACKEND_URL: "http://localhost:8001/metrics?user_id=default",
  CHAT_THREAD_URL: "http://localhost:8001/chat/thread?user_id=default",
  CHAT_SEND_URL: "http://localhost:8001/chat/message?user_id=default",
  SEND_INTERVAL_MS: 60 * 1000,
  MAX_QUEUE: 30,
};

const state = {
  pendingSnapshots: [],
  deliveryQueue: [],
  minuteTabSwitches: 0,
  lastActiveTabId: null,
  currentTabMeta: { domain: null, path: null, title: null },
  lastState: null,
  chatMessages: [],
  chatUnreadCount: 0,
};

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function weightedMean(records, meanKey, countKey) {
  const total = records.reduce((sum, item) => sum + (item[countKey] || 0), 0);
  if (!total) return average(records.map((item) => item[meanKey] || 0));
  return records.reduce((sum, item) => sum + (item[meanKey] || 0) * (item[countKey] || 0), 0) / total;
}

function aggregateMinute(records) {
  if (!records.length) {
    return null;
  }

  const elapsed = Math.max(...records.map((record) => record.window_duration_s || 60), 60);
  const domain = state.currentTabMeta.domain || records[records.length - 1].active_domain || null;
  const path = state.currentTabMeta.path || records[records.length - 1].active_path || null;
  const title = state.currentTabMeta.title || records[records.length - 1].page_title || null;

  return {
    timestamp: new Date().toISOString(),
    window_duration_s: elapsed,
    app_name: "browser",
    active_domain: domain,
    active_path: path,
    page_title: title,
    key_count: records.reduce((sum, item) => sum + (item.key_count || 0), 0),
    character_count: records.reduce((sum, item) => sum + (item.character_count || 0), 0),
    backspace_count: records.reduce((sum, item) => sum + (item.backspace_count || 0), 0),
    mean_key_hold: Number(weightedMean(records, "mean_key_hold", "key_hold_samples").toFixed(4)),
    std_key_hold: Number(weightedMean(records, "std_key_hold", "key_hold_samples").toFixed(4)),
    key_hold_samples: records.reduce((sum, item) => sum + (item.key_hold_samples || 0), 0),
    mean_interkey_latency: Number(weightedMean(records, "mean_interkey_latency", "interkey_samples").toFixed(4)),
    std_interkey_latency: Number(weightedMean(records, "std_interkey_latency", "interkey_samples").toFixed(4)),
    interkey_samples: records.reduce((sum, item) => sum + (item.interkey_samples || 0), 0),
    typing_active_seconds: Number(records.reduce((sum, item) => sum + (item.typing_active_seconds || 0), 0).toFixed(2)),
    active_seconds: Number(records.reduce((sum, item) => sum + (item.active_seconds || 0), 0).toFixed(2)),
    idle_seconds: Number(records.reduce((sum, item) => sum + (item.idle_seconds || 0), 0).toFixed(2)),
    idle_bursts: records.reduce((sum, item) => sum + (item.idle_bursts || 0), 0),
    tab_switches: state.minuteTabSwitches,
    window_switches: state.minuteTabSwitches,
    short_video_seconds: Number(records.reduce((sum, item) => sum + (item.short_video_seconds || 0), 0).toFixed(2)),
    short_video_sessions: records.reduce((sum, item) => sum + (item.short_video_sessions || 0), 0),
  };
}

async function sendPayload(payload) {
  const response = await fetch(CONFIG.BACKEND_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Backend error ${response.status}`);
  }
  return response.json();
}

async function fetchChatThread(markRead = false) {
  const url = `${CONFIG.CHAT_THREAD_URL}&mark_read=${markRead ? "true" : "false"}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Chat thread fetch failed ${response.status}`);
  }
  const payload = await response.json();
  state.chatMessages = payload.messages || [];
  state.chatUnreadCount = payload.unread_count || 0;
  chrome.storage.local.set({
    chat_messages: state.chatMessages,
    chat_unread_count: state.chatUnreadCount,
  });
  return payload;
}

async function sendChatReply(action, payload = {}) {
  const response = await fetch(CONFIG.CHAT_SEND_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quick_reply_action: action,
      quick_reply_payload: payload,
    }),
  });
  if (!response.ok) {
    throw new Error(`Chat reply failed ${response.status}`);
  }
  const data = await response.json();
  if (data.assistant_messages?.length || data.user_message) {
    await fetchChatThread(false);
  }
  return data;
}

async function flushQueue() {
  while (state.deliveryQueue.length) {
    const payload = state.deliveryQueue[0];
    try {
      const response = await sendPayload(payload);
      state.deliveryQueue.shift();
      state.lastState = response.state;
      updateBadge(response.state);
      maybeNotify(response.state);
      chrome.storage.local.set({ last_state: response.state, pending_queue: state.deliveryQueue });
    } catch (error) {
      console.warn("[NeuroLens] backend unavailable, keeping payload queued", error);
      break;
    }
  }
}

function queuePayload(payload) {
  state.deliveryQueue.push(payload);
  if (state.deliveryQueue.length > CONFIG.MAX_QUEUE) {
    state.deliveryQueue.shift();
  }
  chrome.storage.local.set({ pending_queue: state.deliveryQueue });
}

function updateBadge(liveState) {
  const severity = Math.max(liveState.fatigue_score || 0, liveState.load_score || 0);
  const text = String(Math.round(severity));
  const color =
    severity >= 80 ? "#dc2626" :
      severity >= 65 ? "#f97316" :
        severity >= 40 ? "#eab308" : "#16a34a";

  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

function maybeNotify(liveState) {
  const notification = liveState?.notification;
  if (!notification) return;

  chrome.notifications.create(`neurolens-${notification.created_at}`, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: notification.title,
    message: notification.body,
    priority: notification.severity === "critical" ? 2 : 1,
  });
}

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  if (state.lastActiveTabId !== null && state.lastActiveTabId !== tabId) {
    state.minuteTabSwitches += 1;
  }
  state.lastActiveTabId = tabId;
  try {
    const tab = await chrome.tabs.get(tabId);
    const url = new URL(tab.url || "https://localhost");
    state.currentTabMeta = {
      domain: url.hostname,
      path: url.pathname,
      title: tab.title || "",
    };
  } catch (_) {
    state.currentTabMeta = { domain: null, path: null, title: null };
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "TAB_MINUTE_SNAPSHOT") {
    state.pendingSnapshots.push(message.data);
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "GET_STATUS") {
    sendResponse({
      state: state.lastState,
      queueSize: state.deliveryQueue.length,
      chatMessages: state.chatMessages,
      chatUnreadCount: state.chatUnreadCount,
    });
    return true;
  }

  if (message.type === "CHAT_REPLY") {
    sendChatReply(message.action, message.payload || {})
      .then(() => fetchChatThread(false))
      .then((thread) => sendResponse({ ok: true, thread }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message.type === "CHAT_MARK_READ") {
    fetchChatThread(true)
      .then((thread) => sendResponse({ ok: true, thread }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  return false;
});

async function aggregateAndShip() {
  const minuteRecords = state.pendingSnapshots.splice(0, state.pendingSnapshots.length);
  const payload = aggregateMinute(minuteRecords);
  state.minuteTabSwitches = 0;
  if (!payload) return;

  queuePayload(payload);
  await flushQueue();
  await fetchChatThread(false).catch(() => {});
}

chrome.alarms.create("ship-minute-telemetry", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "ship-minute-telemetry") {
    aggregateAndShip().catch((error) => console.warn("[NeuroLens] failed to aggregate", error));
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("ship-minute-telemetry", { periodInMinutes: 1 });
});

chrome.storage.local.get(["pending_queue", "last_state"], (stored) => {
  state.deliveryQueue = Array.isArray(stored.pending_queue) ? stored.pending_queue : [];
  state.lastState = stored.last_state || null;
  state.chatMessages = Array.isArray(stored.chat_messages) ? stored.chat_messages : [];
  state.chatUnreadCount = Number(stored.chat_unread_count || 0);
  if (state.lastState) {
    updateBadge(state.lastState);
  }
  flushQueue().catch(() => {});
  fetchChatThread(false).catch(() => {});
});
