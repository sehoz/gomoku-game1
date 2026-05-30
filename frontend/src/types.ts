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
  players: number;
  max_players: number;
  spectators_count: number;
  max_spectators: number;
  spectators: SpectatorSeat[];
  black_player: number | null;
  black_player_name: string | null;
  black_ready: boolean;
  white_player: number | null;
  white_player_name: string | null;
  white_ready: boolean;
  winner: string;
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
