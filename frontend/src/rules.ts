import type { GameStatus, Move, RuleSet, StoneColor } from "./types";

interface RuleCheck {
  ok: boolean;
  reason?: string;
  status?: GameStatus;
  winner?: StoneColor;
  forbidden?: boolean;
}

const directions = [
  [1, 0],
  [0, 1],
  [1, 1],
  [1, -1],
] as const;

const key = (x: number, y: number) => `${x},${y}`;
const inside = (x: number, y: number, size = 15) => x >= 0 && y >= 0 && x < size && y < size;

function boardFrom(stones: Move[]) {
  return new Map(stones.map((stone) => [key(stone.x, stone.y), stone.color]));
}

function count(board: Map<string, StoneColor>, x: number, y: number, dx: number, dy: number, color: StoneColor) {
  let total = 0;
  let cx = x + dx;
  let cy = y + dy;
  while (board.get(key(cx, cy)) === color) {
    total += 1;
    cx += dx;
    cy += dy;
  }
  return total;
}

function lineCells(board: Map<string, StoneColor>, x: number, y: number, dx: number, dy: number, size: number) {
  const cells: string[] = [];
  for (let offset = -5; offset <= 5; offset += 1) {
    const cx = x + dx * offset;
    const cy = y + dy * offset;
    const value = board.get(key(cx, cy));
    if (!inside(cx, cy, size)) cells.push("X");
    else if (!value) cells.push(".");
    else cells.push(value === "black" ? "B" : "W");
  }
  return cells;
}

function windowIncludesCenter(start: number, length: number) {
  return start <= 5 && 5 < start + length;
}

function hasFour(cells: string[]) {
  for (let i = 0; i <= cells.length - 5; i += 1) {
    if (!windowIncludesCenter(i, 5)) continue;
    const w = cells.slice(i, i + 5);
    if (w.filter((c) => c === "B").length === 4 && w.includes(".")) return true;
  }
  return false;
}

function hasThree(cells: string[]) {
  const patterns = new Set([".BBB.", ".BB.B.", ".B.BB."]);
  for (let size = 5; size <= 6; size += 1) {
    for (let i = 0; i <= cells.length - size; i += 1) {
      if (i <= 5 && 5 < i + size && patterns.has(cells.slice(i, i + size).join(""))) return true;
    }
  }
  return false;
}

export function nextTurn(stones: Move[]): StoneColor {
  return stones.length % 2 === 0 ? "black" : "white";
}

export function opponent(color: StoneColor): StoneColor {
  return color === "black" ? "white" : "black";
}

export function validateMove(stones: Move[], x: number, y: number, color: StoneColor, ruleSet: RuleSet, size = 15): RuleCheck {
  const board = boardFrom(stones);
  if (!inside(x, y, size)) return { ok: false, reason: "落子超出棋盘范围" };
  if (board.has(key(x, y))) return { ok: false, reason: "该交点已有棋子" };
  if (ruleSet !== "renju" || color !== "black") return { ok: true };
  const nextBoard = boardFrom([...stones, { x, y, color }]);
  const lengths = directions.map(([dx, dy]) => 1 + count(nextBoard, x, y, dx, dy, color) + count(nextBoard, x, y, -dx, -dy, color));
  if (lengths.some((length) => length > 5)) return { ok: true, reason: "黑棋长连禁手，白棋获胜", status: "white_win", winner: "white", forbidden: true };
  if (lengths.some((length) => length === 5)) return { ok: true };
  let fours = 0;
  let threes = 0;
  for (const [dx, dy] of directions) {
    const cells = lineCells(nextBoard, x, y, dx, dy, size);
    fours += hasFour(cells) ? 1 : 0;
    threes += hasThree(cells) ? 1 : 0;
  }
  if (fours >= 2) return { ok: true, reason: "黑棋双四禁手，白棋获胜", status: "white_win", winner: "white", forbidden: true };
  if (threes >= 2) return { ok: true, reason: "黑棋双三禁手，白棋获胜", status: "white_win", winner: "white", forbidden: true };
  return { ok: true };
}

export function evaluateMove(stones: Move[], x: number, y: number, color: StoneColor, ruleSet: RuleSet, size = 15): RuleCheck & { status: GameStatus } {
  const validation = validateMove(stones, x, y, color, ruleSet, size);
  if (!validation.ok) return { ...validation, status: "playing" as GameStatus };
  if (validation.forbidden) return { ...validation, status: validation.status || "white_win" };
  const board = boardFrom([...stones, { x, y, color }]);
  const maxLine = Math.max(...directions.map(([dx, dy]) => 1 + count(board, x, y, dx, dy, color) + count(board, x, y, -dx, -dy, color)));
  const wins = ruleSet === "renju" && color === "black" ? maxLine === 5 : maxLine >= 5;
  if (wins) return { ok: true, status: `${color}_win` as GameStatus, winner: color };
  if (stones.length + 1 >= size * size) return { ok: true, status: "draw" as GameStatus };
  return { ok: true, status: "playing" as GameStatus };
}
