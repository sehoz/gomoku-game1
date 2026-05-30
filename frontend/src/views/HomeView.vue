<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Bot, LogIn, RefreshCw, Swords, UserRound, UsersRound, Trophy } from "lucide-vue-next";
import { api } from "../api";
import AuthModal from "../components/AuthModal.vue";
import Avatar from "../components/Avatar.vue";
import { authState, isAuthenticated } from "../stores/auth";
import { presenceState, refreshPresence } from "../stores/presence";

const router = useRouter();
const authOpen = ref(false);
const refreshingOnline = ref(false);
const roomCount = ref(0);
let roomCountTimer: number | null = null;

function enterOnline() {
  if (!isAuthenticated()) {
    authOpen.value = true;
    return;
  }
  router.push("/rooms");
}

async function refreshOnline() {
  refreshingOnline.value = true;
  try {
    await refreshPresence();
  } finally {
    refreshingOnline.value = false;
  }
}

async function refreshRoomCount() {
  try {
    const data = await api.roomCount();
    roomCount.value = data.count;
  } catch {
    roomCount.value = 0;
  }
}

onMounted(() => {
  void refreshRoomCount();
  roomCountTimer = window.setInterval(refreshRoomCount, 1000);
});

onUnmounted(() => {
  if (roomCountTimer !== null) window.clearInterval(roomCountTimer);
});
</script>

<template>
  <main class="home-page">
    <section class="home-topbar">
      <div>
        <p class="eyebrow">Gomoku</p>
        <h1>五子棋对战</h1>
      </div>
      <div class="home-account-actions">
        <RouterLink class="profile-pill" to="/profile">
          <Avatar :username="authState.user?.username || '游客'" />
          <span>{{ authState.user?.username || "游客" }}</span>
          <UserRound :size="18" />
        </RouterLink>
        <button v-if="!isAuthenticated()" class="primary-button" type="button" @click="authOpen = true"><LogIn :size="18" />登录</button>
      </div>
    </section>
    <section class="home-grid">
      <RouterLink class="mode-card" to="/solo">
        <span class="mode-icon"><Bot :size="28" /></span>
        <span><strong>单机对战</strong><small>游客可玩，支持 AI、胜负判定和禁手规则</small></span>
        <Swords :size="22" />
      </RouterLink>
      <button class="mode-card mode-button" :class="{ locked: !isAuthenticated() }" type="button" @click="enterOnline">
        <span class="mode-icon"><UsersRound :size="28" /></span>
        <span>
          <strong>联机对战 <em class="mode-count">{{ roomCount }} 个房间</em></strong>
          <small>{{ isAuthenticated() ? "创建或加入联机房间" : "登录后可进入联机房间" }}</small>
        </span>
        <Swords :size="22" />
      </button>
    </section>
    <section class="online-panel">
      <div class="section-title-row">
        <div><h2>在线列表</h2><p>{{ presenceState.connected ? "实时在线玩家" : "正在连接在线状态" }}</p></div>
        <div class="section-actions">
          <span class="online-count">{{ presenceState.users.length }}</span>
          <button class="icon-button" type="button" title="刷新在线列表" @click="refreshOnline">
            <RefreshCw :size="17" :class="{ spinning: refreshingOnline }" />
          </button>
        </div>
      </div>
      <div v-if="presenceState.users.length === 0" class="empty-state">暂无登录玩家在线。</div>
      <div v-else class="online-list">
        <div v-for="user in presenceState.users" :key="user.id" class="online-row">
          <div class="online-user"><Avatar :username="user.username" /><div><strong>{{ user.username }}</strong><span>ID：{{ user.id }}</span></div></div>
          <div class="online-stats"><span><Trophy :size="15" />{{ user.stats.wins }} 胜</span><span>胜率 {{ user.stats.winRate }}%</span></div>
        </div>
      </div>
    </section>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
  </main>
</template>
