<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RotateCcw, Undo2 } from "lucide-vue-next";
import GameBoard from "../components/GameBoard.vue";
import { evaluateMove, nextTurn, opponent } from "../rules";
import { playStoneSound } from "../stores/settings";
import type { AiLevel, GameStatus, Move, RuleSet, StoneColor } from "../types";

type SoloMode = "self" | AiLevel;

const stones = ref<Move[]>([]);
const ruleSet = ref<RuleSet>("standard");
const aiLevel = ref<SoloMode>("normal");
const playerColor = ref<StoneColor>("black");
const status = ref<GameStatus>("playing");
const message = ref("黑棋先手，请在交点处落子。");
const thinking = ref(false);
const lastPlayerMoveIndex = ref<number | null>(null);
const aiRequestId = ref(0);
const turn = computed(() => nextTurn(stones.value));
const selfPlay = computed(() => aiLevel.value === "self");
const aiColor = computed(() => opponent(playerColor.value));
const playerTurn = computed(() => status.value === "playing" && !thinking.value && (selfPlay.value || turn.value === playerColor.value));
const positionLabel = computed(() => (selfPlay.value ? "自控双方" : playerColor.value === "black" ? "黑棋" : "白棋"));
const localDirections = [
  [1, 0],
  [0, 1],
  [1, 1],
  [1, -1],
] as const;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
const statusLabel = computed(() => {
  if (thinking.value) return "AI 思考中";
  if (selfPlay.value && status.value === "playing") return "自控对局";
  return {
    playing: "进行中",
    black_win: "黑棋获胜",
    white_win: "白棋获胜",
    draw: "平局",
  }[status.value];
});

function colorLabel(color: StoneColor) {
  return color === "black" ? "黑棋" : "白棋";
}

function turnMessage() {
  if (selfPlay.value) return `自控模式，轮到${colorLabel(turn.value)}落子。`;
  return turn.value === playerColor.value ? "轮到你落子。" : "AI 思考中。";
}

function localLineScore(x: number, y: number, color: StoneColor) {
  const board = new Map(stones.value.map((stone) => [`${stone.x},${stone.y}`, stone.color]));
  board.set(`${x},${y}`, color);
  let score = 0;
  for (const [dx, dy] of localDirections) {
    let count = 1;
    let openEnds = 0;
    for (const sign of [-1, 1]) {
      let cx = x + dx * sign;
      let cy = y + dy * sign;
      while (cx >= 0 && cy >= 0 && cx < 15 && cy < 15 && board.get(`${cx},${cy}`) === color) {
        count += 1;
        cx += dx * sign;
        cy += dy * sign;
      }
      if (cx >= 0 && cy >= 0 && cx < 15 && cy < 15 && !board.has(`${cx},${cy}`)) openEnds += 1;
    }
    if (count >= 5) score += 1_000_000;
    else if (count === 4 && openEnds === 2) score += 240_000;
    else if (count === 4 && openEnds === 1) score += 90_000;
    else if (count === 3 && openEnds === 2) score += 34_000;
    else if (count === 3 && openEnds === 1) score += 8_000;
    else if (count === 2 && openEnds === 2) score += 2_400;
    else score += count * 80 + openEnds * 30;
  }
  return score;
}

function localAiMove() {
  const moves = [];
  const occupied = new Set(stones.value.map((stone) => `${stone.x},${stone.y}`));
  for (let y = 0; y < 15; y += 1) {
    for (let x = 0; x < 15; x += 1) {
      if (occupied.has(`${x},${y}`)) continue;
      const result = evaluateMove(stones.value, x, y, aiColor.value, ruleSet.value);
      if (result.ok) moves.push({ x, y, result });
    }
  }
  const safeMoves = moves.filter((move) => !move.result.forbidden);
  const pool = safeMoves.length ? safeMoves : moves;
  const player = playerColor.value;
  const immediateWin = pool.find((move) => evaluateMove(stones.value, move.x, move.y, aiColor.value, ruleSet.value).winner === aiColor.value);
  if (immediateWin) return immediateWin;
  const blockWin = pool.find((move) => evaluateMove(stones.value, move.x, move.y, player, ruleSet.value).winner === player);
  if (blockWin) return blockWin;
  const scored = pool
    .map((move) => ({
      ...move,
      score: localLineScore(move.x, move.y, aiColor.value) * 1.22 + localLineScore(move.x, move.y, player) * 1.08,
    }))
    .sort((a, b) => b.score - a.score);
  if (aiLevel.value === "easy") return scored[Math.floor(Math.random() * Math.min(6, scored.length))] || null;
  return scored[0] || null;
}

function applyAiMove(move: Move, result: { status: string; winner?: StoneColor; reason?: string; forbidden?: boolean }) {
  stones.value.push(move);
  playStoneSound();
  status.value = (result.status as GameStatus) || "playing";
  if (result.reason) {
    message.value = result.reason;
  } else if (result.winner) {
    message.value = result.winner === playerColor.value ? "你赢了。" : "AI 获胜。";
  } else {
    message.value = "轮到你落子。";
  }
}

async function aiPlay() {
  if (selfPlay.value || status.value !== "playing" || turn.value !== aiColor.value || thinking.value) return;
  thinking.value = true;
  const requestId = aiRequestId.value + 1;
  aiRequestId.value = requestId;
  try {
    await sleep(180);
    if (requestId !== aiRequestId.value) return;
    const move = localAiMove();
    if (!move) {
      status.value = "draw";
      message.value = "平局。";
      return;
    }
    applyAiMove({ x: move.x, y: move.y, color: aiColor.value }, move.result);
  } finally {
    if (requestId === aiRequestId.value) thinking.value = false;
  }
}

watch([turn, aiColor, status], aiPlay, { immediate: true });

watch(aiLevel, () => {
  aiRequestId.value += 1;
  thinking.value = false;
  if (selfPlay.value) lastPlayerMoveIndex.value = null;
  if (status.value === "playing") message.value = turnMessage();
  void aiPlay();
});

function play(x: number, y: number) {
  if (!playerTurn.value) return;
  const moveColor = selfPlay.value ? turn.value : playerColor.value;
  const result = evaluateMove(stones.value, x, y, moveColor, ruleSet.value);
  if (!result.ok) {
    message.value = result.reason || "不能落子";
    return;
  }
  if (!selfPlay.value) lastPlayerMoveIndex.value = stones.value.length;
  stones.value.push({ x, y, color: moveColor });
  playStoneSound();
  status.value = result.status;
  if (result.reason) {
    message.value = result.reason;
  } else if (selfPlay.value && result.winner) {
    message.value = `${colorLabel(result.winner)}获胜。`;
  } else if (selfPlay.value) {
    message.value = `轮到${colorLabel(nextTurn(stones.value))}落子。`;
  } else if (result.winner) {
    message.value = result.winner === playerColor.value ? "你赢了。" : "你输了。";
  } else {
    message.value = "AI 思考中。";
  }
}

function reset() {
  aiRequestId.value += 1;
  stones.value = [];
  status.value = "playing";
  thinking.value = false;
  lastPlayerMoveIndex.value = null;
  message.value = selfPlay.value ? "自控模式，轮到黑棋落子。" : "黑棋先手，请在交点处落子。";
}

function undo() {
  if (selfPlay.value) {
    if (stones.value.length === 0) {
      message.value = "当前没有可以悔棋的落子。";
      return;
    }
    stones.value.pop();
    status.value = "playing";
    message.value = `已撤销最后一步，轮到${colorLabel(turn.value)}落子。`;
    return;
  }
  if (lastPlayerMoveIndex.value === null) {
    message.value = "当前没有可以悔棋的落子。";
    return;
  }
  aiRequestId.value += 1;
  thinking.value = false;
  stones.value.splice(lastPlayerMoveIndex.value);
  lastPlayerMoveIndex.value = null;
  status.value = "playing";
  message.value = "已撤销你的上一步落子。";
}
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>单机对战</h1><p>支持无禁手/有禁手规则、AI 强度和玩家棋色。</p></div>
    </header>
    <section class="game-layout">
      <div class="board-panel">
        <div class="board-controlbar solo-controlbar">
          <div class="control-item"><span class="status-label">我的位置</span><strong class="stone-status"><span v-if="!selfPlay" :class="['stone-icon', `stone-icon-${playerColor}`]" />{{ positionLabel }}</strong></div>
          <div class="control-item"><span class="status-label">当前回合</span><strong class="stone-status"><span :class="['stone-icon', `stone-icon-${turn}`]" />{{ turn === "black" ? "黑棋" : "白棋" }}</strong></div>
          <div class="control-item"><span class="status-label">状态</span><strong>{{ statusLabel }}</strong></div>
          <div class="control-actions solo-control-actions">
            <button class="secondary-button" type="button" @click="undo"><Undo2 :size="18" />悔棋</button>
            <button class="secondary-button" type="button" @click="reset"><RotateCcw :size="18" />重新开始</button>
          </div>
        </div>
        <div class="control-notice board-notice" :class="{ warning: message.includes('不可') || message.includes('不能') }">{{ message }}</div>
        <GameBoard :stones="stones" :interactive="playerTurn" @play="play" />
      </div>
      <aside class="settings-panel">
        <h2>对局参数</h2>
        <label>游戏规则<select v-model="ruleSet"><option value="standard">无禁手</option><option value="renju">有禁手</option></select></label>
        <label>AI 强度<select v-model="aiLevel"><option value="self">自己</option><option value="easy">入门</option><option value="normal">标准</option><option value="hard">进阶</option></select></label>
        <label>玩家棋色<select v-model="playerColor" :disabled="selfPlay"><option value="black">执黑</option><option value="white">执白</option></select></label>
      </aside>
    </section>
  </main>
</template>
