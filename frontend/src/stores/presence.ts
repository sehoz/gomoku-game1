import { reactive } from "vue";
import { api, presenceSocketUrl } from "../api";
import { authState } from "./auth";
import type { OnlineUser } from "../types";

export const presenceState = reactive({
  users: [] as OnlineUser[],
  connected: false,
});

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let pollTimer: number | null = null;
let heartbeatTimer: number | null = null;
let activeToken = "";
const fallbackPollMs = 5000;
const heartbeatMs = 15000;

function clearReconnect() {
  if (reconnectTimer === null) return;
  window.clearTimeout(reconnectTimer);
  reconnectTimer = null;
}

function clearPoll() {
  if (pollTimer === null) return;
  window.clearInterval(pollTimer);
  pollTimer = null;
}

function clearHeartbeat() {
  if (heartbeatTimer === null) return;
  window.clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

export async function refreshPresence() {
  try {
    const data = await api.onlineUsers();
    presenceState.users = data.users;
  } catch {
    presenceState.users = [];
  }
}

export function connectPresence() {
  const token = localStorage.getItem("gomoku_token") || "";
  if (socket && activeToken === token && socket.readyState !== WebSocket.CLOSED) return;
  disconnectPresence();
  activeToken = token;
  void refreshPresence();
  socket = new WebSocket(presenceSocketUrl());
  socket.onopen = () => {
    presenceState.connected = true;
    clearPoll();
    socket?.send(JSON.stringify({ type: "ping" }));
    heartbeatTimer = window.setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, heartbeatMs);
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "presence") presenceState.users = data.users;
  };
  socket.onclose = () => {
    presenceState.connected = false;
    clearHeartbeat();
    if (pollTimer === null) pollTimer = window.setInterval(refreshPresence, fallbackPollMs);
    clearReconnect();
    reconnectTimer = window.setTimeout(connectPresence, authState.user ? 3000 : 6000);
  };
  socket.onerror = () => {
    presenceState.connected = false;
    if (pollTimer === null) pollTimer = window.setInterval(refreshPresence, fallbackPollMs);
    void refreshPresence();
  };
}

export function disconnectPresence() {
  clearReconnect();
  clearPoll();
  clearHeartbeat();
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  presenceState.connected = false;
}
