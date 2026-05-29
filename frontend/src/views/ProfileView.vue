<script setup lang="ts">
import { ref } from "vue";
import { BadgeCheck, LogIn, LogOut, Trophy } from "lucide-vue-next";
import AuthModal from "../components/AuthModal.vue";
import Avatar from "../components/Avatar.vue";
import { authState, isAuthenticated, logout } from "../stores/auth";

const authOpen = ref(false);
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
    </section>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
  </main>
</template>
