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
let activeToken = "";

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
  pollTimer = window.setInterval(refreshPresence, 1000);
  socket = new WebSocket(presenceSocketUrl());
  socket.onopen = () => {
    presenceState.connected = true;
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "presence") presenceState.users = data.users;
  };
  socket.onclose = () => {
    presenceState.connected = false;
    clearReconnect();
    reconnectTimer = window.setTimeout(connectPresence, authState.user ? 3000 : 6000);
  };
  socket.onerror = () => {
    presenceState.connected = false;
    void refreshPresence();
  };
}

export function disconnectPresence() {
  clearReconnect();
  clearPoll();
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  presenceState.connected = false;
}
