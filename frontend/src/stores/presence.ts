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
let activeToken = "";

function clearReconnect() {
  if (reconnectTimer === null) return;
  window.clearTimeout(reconnectTimer);
  reconnectTimer = null;
}

async function loadFallback() {
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
    void loadFallback();
  };
}

export function disconnectPresence() {
  clearReconnect();
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  presenceState.connected = false;
}
