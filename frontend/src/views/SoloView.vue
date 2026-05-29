<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RotateCcw } from "lucide-vue-next";
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

async function aiPlay() {
  if (status.value !== "playing" || turn.value !== aiColor.value || thinking.value) return;
  thinking.value = true;
  try {
    const data = await api.soloAiMove({
      stones: stones.value,
      board_size: 15,
      ai_color: aiColor.value,
      rule_set: ruleSet.value,
      ai_level: aiLevel.value,
    });
    if (!data.move) {
      status.value = "draw";
      message.value = "平局。";
      return;
    }
    stones.value.push({ x: data.move.x, y: data.move.y, color: aiColor.value });
    playStoneSound();
    status.value = (data.result.status as GameStatus) || "playing";
    message.value = data.result.winner ? "AI 获胜。" : "轮到你落子。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "AI 请求失败";
  } finally {
    thinking.value = false;
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
  stones.value.push({ x, y, color: playerColor.value });
  playStoneSound();
  status.value = result.status;
  message.value = result.winner ? "你赢了。" : "AI 思考中。";
}

function reset() {
  stones.value = [];
  status.value = "playing";
  message.value = "黑棋先手，请在交点处落子。";
}
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>单机对战</h1><p>支持无禁手/有禁手规则、AI 强度和玩家棋色。</p></div>
      <button class="secondary-button" type="button" @click="reset"><RotateCcw :size="18" />重新开始</button>
    </header>
    <section class="game-layout">
      <div class="board-panel">
        <div class="board-toolbar">
          <div><span class="status-label">当前回合</span><strong>{{ turn === "black" ? "黑棋" : "白棋" }}</strong></div>
          <div><span class="status-label">状态</span><strong>{{ statusLabel }}</strong></div>
          <div><span class="status-label">落子数</span><strong>{{ stones.length }}</strong></div>
        </div>
        <GameBoard :stones="stones" :interactive="playerTurn" @play="play" />
        <div class="game-message" :class="{ warning: message.includes('不可') || message.includes('不能') }">{{ message }}</div>
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
