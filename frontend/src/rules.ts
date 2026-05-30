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

function linePositions(x: number, y: number, dx: number, dy: number, size: number) {
  let sx = x;
  let sy = y;
  while (inside(sx - dx, sy - dy, size)) {
    sx -= dx;
    sy -= dy;
  }
  const positions: Array<[number, number]> = [];
  while (inside(sx, sy, size)) {
    positions.push([sx, sy]);
    sx += dx;
    sy += dy;
  }
  return positions;
}

function hasAll(required: Array<[number, number]>, window: Set<string>) {
  return required.every(([x, y]) => window.has(key(x, y)));
}

function openFourExists(
  board: Map<string, StoneColor>,
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: StoneColor,
  size: number,
  required: Array<[number, number]>,
) {
  const positions = linePositions(x, y, dx, dy, size);
  const values = positions.map(([px, py]) => board.get(key(px, py)) || ".");
  for (let i = 0; i <= values.length - 6; i += 1) {
    const window = values.slice(i, i + 6);
    if (window.join("") !== `.${color}${color}${color}${color}.`) continue;
    if (hasAll(required, new Set(positions.slice(i, i + 6).map(([px, py]) => key(px, py))))) return true;
  }
  return false;
}

function exactFiveExists(
  board: Map<string, StoneColor>,
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: StoneColor,
  size: number,
  required: Array<[number, number]>,
) {
  const positions = linePositions(x, y, dx, dy, size);
  const values = positions.map(([px, py]) => board.get(key(px, py)) || ".");
  const five = `${color}${color}${color}${color}${color}`;
  for (let i = 0; i <= values.length - 5; i += 1) {
    if (values.slice(i, i + 5).join("") !== five) continue;
    if (values[i - 1] === color || values[i + 5] === color) continue;
    if (hasAll(required, new Set(positions.slice(i, i + 5).map(([px, py]) => key(px, py))))) return true;
  }
  return false;
}

function winningExtensionsInDirection(
  board: Map<string, StoneColor>,
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: StoneColor,
  size: number,
  required: Array<[number, number]> = [],
) {
  const wins: Array<[number, number]> = [];
  const baseRequired: Array<[number, number]> = [[x, y], ...required];
  for (const [px, py] of linePositions(x, y, dx, dy, size)) {
    if (board.has(key(px, py))) continue;
    const next = new Map(board);
    next.set(key(px, py), color);
    if (exactFiveExists(next, x, y, dx, dy, color, size, [...baseRequired, [px, py]])) wins.push([px, py]);
  }
  return wins;
}

function directionHasFour(board: Map<string, StoneColor>, x: number, y: number, dx: number, dy: number, color: StoneColor, size: number) {
  return winningExtensionsInDirection(board, x, y, dx, dy, color, size).length > 0;
}

function patternOpenThreeExists(board: Map<string, StoneColor>, x: number, y: number, dx: number, dy: number, color: StoneColor, size: number) {
  const patterns = [
    [".", color, color, color, "."],
    [".", color, color, ".", color, "."],
    [".", color, ".", color, color, "."],
    [".", color, ".", color, ".", color, "."],
  ];
  const positions = linePositions(x, y, dx, dy, size);
  const values = positions.map(([px, py]) => board.get(key(px, py)) || ".");
  for (const pattern of patterns) {
    for (let i = 0; i <= values.length - pattern.length; i += 1) {
      if (values.slice(i, i + pattern.length).every((value, index) => value === pattern[index])) {
        if (positions.slice(i, i + pattern.length).some(([px, py]) => px === x && py === y)) return true;
      }
    }
  }
  return false;
}

function directionHasOpenThree(board: Map<string, StoneColor>, x: number, y: number, dx: number, dy: number, color: StoneColor, size: number) {
  if (patternOpenThreeExists(board, x, y, dx, dy, color, size)) return true;
  for (const [px, py] of linePositions(x, y, dx, dy, size)) {
    if (board.has(key(px, py))) continue;
    const next = new Map(board);
    next.set(key(px, py), color);
    if (openFourExists(next, x, y, dx, dy, color, size, [[x, y], [px, py]])) return true;
    if (winningExtensionsInDirection(next, x, y, dx, dy, color, size, [[px, py]]).length >= 2) return true;
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
    fours += directionHasFour(nextBoard, x, y, dx, dy, color, size) ? 1 : 0;
    threes += directionHasOpenThree(nextBoard, x, y, dx, dy, color, size) ? 1 : 0;
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
