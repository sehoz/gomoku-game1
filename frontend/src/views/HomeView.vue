<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { Bot, LogIn, Swords, UserRound, UsersRound } from "lucide-vue-next";
import AuthModal from "../components/AuthModal.vue";
import Avatar from "../components/Avatar.vue";
import { authState, isAuthenticated } from "../stores/auth";

const router = useRouter();
const authOpen = ref(false);

function enterOnline() {
  if (!isAuthenticated()) {
    authOpen.value = true;
    return;
  }
  router.push("/rooms");
}
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
        <span><strong>联机对战</strong><small>{{ isAuthenticated() ? "创建或加入联机房间" : "登录后可进入联机房间" }}</small></span>
        <Swords :size="22" />
      </button>
    </section>
    <section class="home-status">
      <div><span class="status-label">当前身份</span><strong>{{ isAuthenticated() ? "已登录" : "游客" }}</strong></div>
      <div><span class="status-label">单机</span><strong>已开放</strong></div>
      <div><span class="status-label">联机</span><strong>{{ isAuthenticated() ? "已开放" : "需登录" }}</strong></div>
    </section>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
  </main>
</template>
