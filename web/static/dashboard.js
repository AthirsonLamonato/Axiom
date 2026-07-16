"use strict";

const pollingBlocks = [
  ["status-block", "/api/status-html", 10000],
  ["stats-block", "/api/stats-html", 15000],
  ["reminders-block", "/api/reminders-html", 15000],
  ["context-block", "/api/context-html", 20000],
  ["routines-block", "/api/routines-html", 0],
  ["history-block", "/api/history-html", 8000],
];

const getCsrfToken = () => document.body.dataset.csrf || "";

async function refreshBlock(id, endpoint) {
  const block = document.getElementById(id);
  if (!block || document.hidden) return;
  try {
    const response = await fetch(endpoint, { headers: { "Accept": "text/html" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    block.innerHTML = await response.text();
  } catch {
    block.innerHTML = '<div class="empty">Não foi possível atualizar agora.</div>';
  }
}

async function submitRoutine(endpoint, formData, trigger) {
  if (trigger) trigger.disabled = true;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "X-CSRF-Token": getCsrfToken() },
      body: formData,
    });
    const block = document.getElementById("routines-block");
    if (block) block.innerHTML = await response.text();
  } finally {
    if (trigger && trigger.isConnected) trigger.disabled = false;
  }
}

let cmdWs;
let commandReconnectTimer;

function setConnectionState(label, online = false) {
  const status = document.getElementById("ws-status");
  if (!status) return;
  status.textContent = label;
  status.className = online ? "ok" : "";
}

function connectCommandSocket() {
  clearTimeout(commandReconnectTimer);
  const scheme = location.protocol === "https:" ? "wss://" : "ws://";
  cmdWs = new WebSocket(`${scheme}${location.host}/ws/command`);
  cmdWs.onopen = () => setConnectionState("● online", true);
  cmdWs.onmessage = (event) => {
    if (event.data.startsWith("{")) {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "ping") {
          cmdWs.send(JSON.stringify({ type: "pong" }));
          return;
        }
      } catch { /* resposta HTML comum */ }
    }
    const target = document.getElementById("cmd-response");
    if (target) target.innerHTML = event.data;
  };
  cmdWs.onclose = () => {
    setConnectionState("● reconectando");
    commandReconnectTimer = setTimeout(connectCommandSocket, 2000);
  };
}

function sendCommand() {
  const input = document.getElementById("cmd-input");
  const target = document.getElementById("cmd-response");
  const command = input?.value.trim();
  if (!command || !target) return;
  if (!cmdWs || cmdWs.readyState !== WebSocket.OPEN) {
    target.innerHTML = '<div class="response-box connecting">Reconectando ao servidor...</div>';
    return;
  }
  target.innerHTML = '<div class="response-box connecting">Processando...</div>';
  cmdWs.send(JSON.stringify({ command }));
  input.value = "";
}

let eventWs;
let eventReconnectTimer;

function connectEventSocket() {
  clearTimeout(eventReconnectTimer);
  const scheme = location.protocol === "https:" ? "wss://" : "ws://";
  eventWs = new WebSocket(`${scheme}${location.host}/ws/events`);
  eventWs.onmessage = (event) => {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }
    if (payload.type === "ping") {
      eventWs.send(JSON.stringify({ type: "pong" }));
      return;
    }
    const list = document.getElementById("events-list");
    if (!list) return;
    list.querySelector(".empty")?.remove();
    const row = document.createElement("div");
    const timestamp = document.createElement("span");
    const type = document.createElement("span");
    const safeType = ["reminder", "meeting", "info"].includes(payload.type) ? payload.type : "info";
    row.className = "event-row";
    timestamp.className = "event-ts";
    timestamp.textContent = payload.ts || "";
    type.className = `event-type-${safeType}`;
    type.textContent = `[${safeType}]`;
    row.append(timestamp, type, document.createTextNode(` ${payload.message || ""}`));
    list.prepend(row);
    while (list.children.length > 6) list.lastChild.remove();
  };
  eventWs.onclose = () => {
    eventReconnectTimer = setTimeout(connectEventSocket, 3000);
  };
}

document.addEventListener("DOMContentLoaded", () => {
  pollingBlocks.forEach(([id, endpoint, interval]) => {
    refreshBlock(id, endpoint);
    if (interval) setInterval(() => refreshBlock(id, endpoint), interval);
  });

  document.getElementById("cmd-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") sendCommand();
  });
  document.getElementById("send-command")?.addEventListener("click", sendCommand);

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-post]");
    if (!form) return;
    event.preventDefault();
    submitRoutine(form.dataset.post, new FormData(form), form.querySelector("button[type=submit]"));
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-post]");
    if (!button) return;
    const question = button.dataset.confirm;
    if (question && !window.confirm(question)) return;
    submitRoutine(button.dataset.post, new FormData(), button);
  });

  connectCommandSocket();
  connectEventSocket();
});
