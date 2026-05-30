<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RotateCcw, Undo2 } from "lucide-vue-next";
import { api } from "../api";
import GameBoard from "../components/GameBoard.vue";
import { evaluateMove, nextTurn, opponent } from "../rules";
import { playStoneSound } from "../stores/settings";
import type { AiLevel, GameStatus, Move, RuleSet, StoneColor } from "../types";

const stones = ref<Move[]>([]);
const ruleSet = ref<RuleSet>("standard");
const aiLevel = ref<AiLevel>("normal");
const playerColor = ref<StoneColor>("black");
const status = ref<GameStatus>("playing");
const message = ref("黑棋先手，请在交点处落子。");
const thinking = ref(false);
const lastPlayerMoveIndex = ref<number | null>(null);
const aiRequestId = ref(0);
const turn = computed(() => nextTurn(stones.value));
const aiColor = computed(() => opponent(playerColor.value));
const playerTurn = computed(() => status.value === "playing" && turn.value === playerColor.value);
const statusLabel = computed(() => {
  if (thinking.value) return "AI 思考中";
  return {
    playing: "进行中",
    black_win: "黑棋获胜",
    white_win: "白棋获胜",
    draw: "平局",
  }[status.value];
});

function localRandomAiMove() {
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
  return pool[Math.floor(Math.random() * pool.length)] || null;
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
  if (status.value !== "playing" || turn.value !== aiColor.value || thinking.value) return;
  thinking.value = true;
  const requestId = aiRequestId.value + 1;
  aiRequestId.value = requestId;
  try {
    const data = await api.soloAiMove({
      stones: stones.value,
      board_size: 15,
      ai_color: aiColor.value,
      rule_set: ruleSet.value,
      ai_level: aiLevel.value,
    });
    if (requestId !== aiRequestId.value) return;
    if (!data.move) {
      status.value = "draw";
      message.value = "平局。";
      return;
    }
    applyAiMove({ x: data.move.x, y: data.move.y, color: aiColor.value }, data.result);
  } catch (err) {
    if (requestId !== aiRequestId.value) return;
    const fallback = localRandomAiMove();
    if (!fallback) {
      status.value = "draw";
      message.value = "平局。";
      return;
    }
    applyAiMove({ x: fallback.x, y: fallback.y, color: aiColor.value }, fallback.result);
    if (!fallback.result.reason && !fallback.result.winner) {
      message.value = "AI 已使用本地随机落子。";
    }
  } finally {
    if (requestId === aiRequestId.value) thinking.value = false;
  }
}

watch([turn, aiColor, status], aiPlay, { immediate: true });

function play(x: number, y: number) {
  if (!playerTurn.value) return;
  const result = evaluateMove(stones.value, x, y, playerColor.value, ruleSet.value);
  if (!result.ok) {
    message.value = result.reason || "不能落子";
    return;
  }
  lastPlayerMoveIndex.value = stones.value.length;
  stones.value.push({ x, y, color: playerColor.value });
  playStoneSound();
  status.value = result.status;
  if (result.reason) {
    message.value = result.reason;
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
  message.value = "黑棋先手，请在交点处落子。";
}

function undo() {
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
        <div class="board-controlbar">
          <div class="control-item"><span class="status-label">我的位置</span><strong class="stone-status"><span :class="['stone-icon', `stone-icon-${playerColor}`]" />{{ playerColor === "black" ? "黑棋" : "白棋" }}</strong></div>
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
        <label>AI 强度<select v-model="aiLevel"><option value="easy">入门</option><option value="normal">标准</option><option value="hard">进阶</option></select></label>
        <label>玩家棋色<select v-model="playerColor"><option value="black">执黑</option><option value="white">执白</option></select></label>
      </aside>
    </section>
  </main>
</template>
