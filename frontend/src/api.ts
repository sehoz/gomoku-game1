import type {
  AdminRoom,
  AdminUser,
  AiLevel,
  LeaderboardEntry,
  MatchRecord,
  MatchReplay,
  Move,
  OnlineUser,
  Room,
  RoomInvitation,
  RoomState,
  RuleSet,
  SeatSwitchRequest,
  StoneColor,
  UndoRequest,
  UserProfile,
} from "./types";

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const wsBase = import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000/ws";

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function token() {
  return localStorage.getItem("gomoku_token") || "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token()) {
    headers.set("Authorization", `Token ${token()}`);
  }
  const method = (options.method || "GET").toUpperCase();
  const maxAttempts = method === "GET" ? 3 : 1;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(`${apiBase}${path}`, { ...options, headers });
    } catch {
      if (attempt < maxAttempts) {
        await sleep(220 * attempt);
        continue;
      }
      throw new Error("网络连接不稳定，请稍后重试");
    }
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json().catch(() => ({})) : {};
    if (response.ok) return data;
    if (method === "GET" && response.status >= 500 && attempt < maxAttempts) {
      await sleep(260 * attempt);
      continue;
    }
    const detail = data.detail || Object.values(data).flat().filter(Boolean).join("；");
    if (detail) throw new Error(String(detail));
    if (response.status === 429) throw new Error("请求过于频繁，请稍后再试");
    if (response.status >= 500) throw new Error(`服务器暂时不可用（${response.status}），请稍后重试`);
    throw new Error(`请求失败（${response.status}）`);
  }
  throw new Error("网络连接不稳定，请稍后重试");
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
  async updateProfile(payload: { username?: string; avatar_url?: string }) {
    return request<{ user: UserProfile }>("/profile/", { method: "PATCH", body: JSON.stringify(payload) });
  },
  async changePassword(payload: { old_password: string; new_password: string; confirm_password: string }) {
    return request<{ token: string; user: UserProfile }>("/profile/password/", { method: "POST", body: JSON.stringify(payload) });
  },
  async onlineUsers() {
    return request<{ users: OnlineUser[] }>("/online/");
  },
  async roomCount() {
    return request<{ count: number }>("/rooms/count/");
  },
  async leaderboard() {
    return request<{ entries: LeaderboardEntry[] }>("/leaderboard/");
  },
  async matchHistory() {
    return request<{ records: MatchRecord[] }>("/profile/matches/");
  },
  async matchReplay(id: number) {
    return request<MatchReplay>(`/profile/matches/${id}/`);
  },
  async invitations() {
    return request<{ invitations: RoomInvitation[] }>("/invitations/");
  },
  async respondInvitation(id: number, accepted: boolean) {
    return request<{ invitation: RoomInvitation; room: Room | null }>(`/invitations/${id}/respond/`, {
      method: "POST",
      body: JSON.stringify({ accepted }),
    });
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
  async kickRoomUser(id: number, user_id: number) {
    return request<{ room: Room | null }>(`/rooms/${id}/kick/`, { method: "POST", body: JSON.stringify({ user_id }) });
  },
  async inviteRoomUser(id: number, user_id: number) {
    return request<{ invitation: RoomInvitation }>(`/rooms/${id}/invite/`, { method: "POST", body: JSON.stringify({ user_id }) });
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
  async surrender(id: number) {
    return request<Room>(`/rooms/${id}/surrender/`, { method: "POST" });
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
  async adminUsers() {
    return request<{ users: AdminUser[] }>("/admin/users/");
  },
  async adminCreateUser(payload: { username: string; password: string; email?: string; is_active?: boolean; is_staff?: boolean; is_superuser?: boolean }) {
    return request<{ user: AdminUser }>("/admin/users/", { method: "POST", body: JSON.stringify(payload) });
  },
  async adminUpdateUser(id: number, payload: Partial<AdminUser> & { password?: string }) {
    return request<{ user: AdminUser }>(`/admin/users/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
  },
  async adminDeleteUser(id: number) {
    return request<{ ok: boolean }>(`/admin/users/${id}/`, { method: "DELETE" });
  },
  async adminRooms() {
    return request<{ rooms: AdminRoom[] }>("/admin/rooms/");
  },
  async adminUpdateRoom(id: number, payload: Partial<AdminRoom> & { password?: string }) {
    return request<{ room: AdminRoom }>(`/admin/rooms/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
  },
  async adminDeleteRoom(id: number) {
    return request<{ ok: boolean }>(`/admin/rooms/${id}/`, { method: "DELETE" });
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
