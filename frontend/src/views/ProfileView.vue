<script setup lang="ts">
import { onMounted, ref } from "vue";
import { BadgeCheck, Clock3, LogIn, LogOut, Trophy } from "lucide-vue-next";
import { api } from "../api";
import AuthModal from "../components/AuthModal.vue";
import Avatar from "../components/Avatar.vue";
import { authState, isAuthenticated, logout } from "../stores/auth";
import type { MatchRecord } from "../types";

const authOpen = ref(false);
const records = ref<MatchRecord[]>([]);
const historyError = ref("");

function resultLabel(record: MatchRecord) {
  if (record.result === "win") return "胜";
  if (record.result === "loss") return "负";
  if (record.result === "draw") return "平";
  return "未完成";
}

function colorLabel(color: string) {
  return color === "black" ? "黑棋" : "白棋";
}

function formatTime(value: string | null) {
  if (!value) return "未记录";
  return new Date(value).toLocaleString();
}

async function loadHistory() {
  if (!isAuthenticated()) return;
  try {
    const data = await api.matchHistory();
    records.value = data.records;
  } catch (err) {
    historyError.value = err instanceof Error ? err.message : "对局记录加载失败";
  }
}

onMounted(loadHistory);
</script>

<template>
  <main class="page-shell">
    <header class="page-header"><div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>个人信息</h1><p>{{ isAuthenticated() ? "账号资料和对局统计。" : "当前为游客状态。" }}</p></div></header>
    <section class="profile-layout">
      <div class="profile-card">
        <Avatar :username="authState.user?.username || '游客'" size="lg" />
        <div><h2>{{ authState.user?.username || "游客" }}</h2><p>ID：{{ authState.user?.id || "guest" }}</p></div>
        <span class="tag"><BadgeCheck :size="14" />{{ isAuthenticated() ? "已登录" : "游客" }}</span>
        <button v-if="isAuthenticated()" class="secondary-button" type="button" @click="logout"><LogOut :size="18" />退出登录</button>
        <button v-else class="primary-button" type="button" @click="authOpen = true"><LogIn :size="18" />登录</button>
      </div>
      <div class="profile-stats">
        <div><Trophy :size="22" /><span>总对局</span><strong>{{ authState.user?.stats.totalGames || 0 }}</strong></div>
        <div><BadgeCheck :size="22" /><span>胜场</span><strong>{{ authState.user?.stats.wins || 0 }}</strong></div>
        <div><BadgeCheck :size="22" /><span>胜率</span><strong>{{ authState.user?.stats.winRate || 0 }}%</strong></div>
      </div>
      <section v-if="isAuthenticated()" class="history-panel">
        <div class="section-title-row"><div><h2>近期对局</h2><p>记录每局开始、结束、对手和结果。</p></div><Clock3 :size="22" /></div>
        <div v-if="historyError" class="game-message warning">{{ historyError }}</div>
        <div v-else-if="records.length === 0" class="empty-state">暂无已结束对局。</div>
        <div v-else class="history-list">
          <article v-for="record in records" :key="record.id" class="history-row">
            <div><strong>{{ record.room_name }}</strong><span>{{ colorLabel(record.color) }} · 对手：{{ record.opponent.username }}</span></div>
            <div><span>开始：{{ formatTime(record.started_at) }}</span><span>结束：{{ formatTime(record.ended_at) }}</span></div>
            <span :class="['result-badge', record.result]">{{ resultLabel(record) }}</span>
          </article>
        </div>
      </section>
    </section>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
  </main>
</template>
