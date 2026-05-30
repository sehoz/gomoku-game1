export type RuleSet = "standard" | "renju";
export type AiLevel = "easy" | "normal" | "hard";
export type StoneColor = "black" | "white";
export type GameStatus = "playing" | "black_win" | "white_win" | "draw";

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  stats: {
    totalGames: number;
    wins: number;
    losses: number;
    draws: number;
    winRate: number;
  };
}

export interface Room {
  id: number;
  name: string;
  created_at: string;
  has_password: boolean;
  rule_set: RuleSet;
  status: "waiting" | "playing" | "finished";
  current_game: CurrentGame | null;
  players: number;
  max_players: number;
  spectators_count: number;
  max_spectators: number;
  move_time_seconds: number;
  total_time_seconds: number;
  spectators: SpectatorSeat[];
  black_player: number | null;
  black_player_name: string | null;
  black_ready: boolean;
  black_undo_remaining: number;
  white_player: number | null;
  white_player_name: string | null;
  white_ready: boolean;
  white_undo_remaining: number;
  winner: string;
  pending_undo_request: UndoRequest | null;
  pending_seat_switch_request: SeatSwitchRequest | null;
}

export interface UndoRequest {
  user_id: number;
  username: string;
  color: StoneColor;
}

export interface SeatSwitchRequest {
  requester_id: number;
  requester_username: string;
  target_user_id: number;
  target_username: string;
  from_seat: string;
  from_label: string;
  target_seat: string;
  target_label: string;
}

export interface CurrentGame {
  id: number;
  status: "playing" | "finished";
  winner: string;
  end_reason: string;
  started_at: string;
  ended_at: string | null;
  move_time_seconds: number;
  total_time_seconds: number;
  black_time_left_seconds: number;
  white_time_left_seconds: number;
  turn_started_at: string | null;
}

export interface SpectatorSeat {
  user: number;
  username: string;
  seat_number: number;
  stats: UserProfile["stats"];
}

export interface Move {
  id?: number;
  move_number?: number;
  x: number;
  y: number;
  color: StoneColor;
  player?: number;
  created_at?: string;
}

export interface ChatMessage {
  id: number;
  sender: number | null;
  sender_name: string;
  text: string;
  created_at: string;
}

export interface RoomState {
  room: Room;
  moves: Move[];
  messages: ChatMessage[];
}

export type OnlineUser = UserProfile;

export interface MatchRecord {
  id: number;
  room_name: string;
  rule_set: RuleSet;
  color: StoneColor;
  result: "win" | "loss" | "draw" | "unfinished";
  opponent: { id: number | null; username: string };
  started_at: string | null;
  ended_at: string | null;
  end_reason: string;
  moves_count: number;
}
