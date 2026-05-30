import type { AiLevel, MatchRecord, Move, OnlineUser, Room, RoomState, RuleSet, SeatSwitchRequest, StoneColor, UndoRequest, UserProfile } from "./types";

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const wsBase = import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000/ws";

export function token() {
  return localStorage.getItem("gomoku_token") || "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token()) {
    headers.set("Authorization", `Token ${token()}`);
  }
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, { ...options, headers });
  } catch {
    throw new Error("无法连接服务器，请稍后重试");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || Object.values(data).flat().join("；");
    throw new Error(detail || "请求失败");
  }
  return data;
}

export const api = {
  async register(username: string, password: string) {
    return request<{ token: string; user: UserProfile }>("/auth/register/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  async login(username: string, password: string) {
    return request<{ token: string; user: UserProfile }>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  async logout() {
    return request<{ ok: boolean }>("/auth/logout/", { method: "POST" });
  },
  async me() {
    return request<{ user: UserProfile | null }>("/auth/me/");
  },
  async onlineUsers() {
    return request<{ users: OnlineUser[] }>("/online/");
  },
  async roomCount() {
    return request<{ count: number }>("/rooms/count/");
  },
  async matchHistory() {
    return request<{ records: MatchRecord[] }>("/profile/matches/");
  },
  async rooms() {
    return request<Room[]>("/rooms/");
  },
  async createRoom(payload: { name: string; rule_set: RuleSet; has_password: boolean; password?: string; move_time_seconds: number; total_time_seconds: number }) {
    return request<Room>("/rooms/", { method: "POST", body: JSON.stringify(payload) });
  },
  async joinRoom(id: number, password = "") {
    return request<Room>(`/rooms/${id}/join/`, { method: "POST", body: JSON.stringify({ password }) });
  },
  async leaveRoom(id: number) {
    return request<{ room: Room | null }>(`/rooms/${id}/leave/`, { method: "POST" });
  },
  async roomState(id: number) {
    return request<RoomState>(`/rooms/${id}/state/`);
  },
  async switchSeat(id: number, target_color: StoneColor) {
    return request<Room>(`/rooms/${id}/switch-seat/`, { method: "POST", body: JSON.stringify({ target_color }) });
  },
  async switchPosition(id: number, target_seat: string) {
    return request<Room>(`/rooms/${id}/switch-seat/`, { method: "POST", body: JSON.stringify({ target_seat }) });
  },
  async readyRoom(id: number, ready: boolean) {
    return request<Room>(`/rooms/${id}/ready/`, { method: "POST", body: JSON.stringify({ ready }) });
  },
  async move(id: number, x: number, y: number) {
    return request(`/rooms/${id}/move/`, { method: "POST", body: JSON.stringify({ x, y }) });
  },
  async chat(id: number, text: string) {
    return request(`/rooms/${id}/chat/`, { method: "POST", body: JSON.stringify({ text }) });
  },
  async requestUndo(id: number) {
    return request<{ request: UndoRequest }>(`/rooms/${id}/undo/request/`, { method: "POST" });
  },
  async respondUndo(id: number, accepted: boolean) {
    return request<{ accepted: boolean; detail: string }>(`/rooms/${id}/undo/respond/`, { method: "POST", body: JSON.stringify({ accepted }) });
  },
  async respondSeatSwitch(id: number, accepted: boolean) {
    return request<{ accepted: boolean; detail: string; request?: SeatSwitchRequest }>(`/rooms/${id}/seat-switch/respond/`, {
      method: "POST",
      body: JSON.stringify({ accepted }),
    });
  },
  async soloAiMove(payload: {
    stones: Move[];
    board_size: number;
    ai_color: StoneColor;
    rule_set: RuleSet;
    ai_level: AiLevel;
  }) {
    return request<{ move: Move | null; result: { ok: boolean; status: string; winner?: StoneColor; reason?: string } }>(
      "/solo/ai-move/",
      { method: "POST", body: JSON.stringify(payload) },
    );
  },
};

export function roomSocketUrl(roomId: number) {
  return `${wsBase}/rooms/${roomId}/?token=${encodeURIComponent(token())}`;
}

export function presenceSocketUrl() {
  const query = token() ? `?token=${encodeURIComponent(token())}` : "";
  return `${wsBase}/presence/${query}`;
}
