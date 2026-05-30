<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Lock, Plus, RefreshCw, Unlock, UsersRound } from "lucide-vue-next";
import { api } from "../api";
import AuthModal from "../components/AuthModal.vue";
import Modal from "../components/Modal.vue";
import { isAuthenticated } from "../stores/auth";
import type { Room, RuleSet } from "../types";

const router = useRouter();
const rooms = ref<Room[]>([]);
const error = ref("");
const loading = ref(false);
const authOpen = ref(false);
const createOpen = ref(false);
const joinRoom = ref<Room | null>(null);
const createError = ref("");
const joinError = ref("");
const password = ref("");
const form = ref({
  name: "好友对局",
  rule_set: "standard" as RuleSet,
  has_password: false,
  password: "",
  move_time_seconds: 30,
  total_time_minutes: 10,
});
let refreshTimer: number | null = null;

async function load(showSpinner = true) {
  if (!isAuthenticated()) return;
  if (showSpinner) loading.value = true;
  try {
    rooms.value = await api.rooms();
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "房间列表加载失败";
  } finally {
    if (showSpinner) loading.value = false;
  }
}

function timeAgo(value: string) {
  const diff = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

async function enter(room: Room) {
  error.value = "";
  if (room.has_password) {
    password.value = "";
    joinError.value = "";
    joinRoom.value = room;
    return;
  }
  try {
    const next = await api.joinRoom(room.id);
    router.push(`/rooms/${next.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加入失败";
  }
}

async function submitJoin() {
  if (!joinRoom.value) return;
  joinError.value = "";
  try {
    const next = await api.joinRoom(joinRoom.value.id, password.value);
    router.push(`/rooms/${next.id}`);
  } catch (err) {
    joinError.value = err instanceof Error ? err.message : "加入失败";
  }
}

async function create() {
  const name = form.value.name.trim();
  createError.value = "";
  if (rooms.value.some((room) => room.name.trim().toLowerCase() === name.toLowerCase())) {
    createError.value = "房间名重复";
    return;
  }
  try {
    const room = await api.createRoom({
      name,
      rule_set: form.value.rule_set,
      has_password: form.value.has_password,
      password: form.value.password,
      move_time_seconds: Number(form.value.move_time_seconds),
      total_time_seconds: Number(form.value.total_time_minutes) * 60,
    });
    router.push(`/rooms/${room.id}`);
  } catch (err) {
    createError.value = err instanceof Error ? err.message : "创建失败";
  }
}

function roomFull(room: Room) {
  return room.players >= room.max_players && room.spectators_count >= room.max_spectators;
}

function enterLabel(room: Room) {
  if (roomFull(room)) return "已满";
  return room.players >= room.max_players ? "观战" : "进入";
}

onMounted(() => {
  void load();
  refreshTimer = window.setInterval(() => void load(false), 1000);
});
onUnmounted(() => {
  if (refreshTimer !== null) window.clearInterval(refreshTimer);
});
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>联机对战</h1><p>登录后可以创建或加入房间。</p></div>
      <div v-if="isAuthenticated()" class="header-actions">
        <button class="secondary-button" type="button" @click="load()"><RefreshCw :size="18" :class="{ spinning: loading }" />刷新列表</button>
        <button class="primary-button" type="button" @click="createOpen = true; createError = ''"><Plus :size="18" />创建房间</button>
      </div>
    </header>
    <section v-if="!isAuthenticated()" class="locked-panel">
      <UsersRound :size="34" />
      <div><h2>请先登录</h2><p>游客可以单机，联机需要账号身份。</p></div>
      <button class="primary-button" type="button" @click="authOpen = true">登录账号</button>
    </section>
    <template v-else>
      <div v-if="error" class="game-message warning">{{ error }}</div>
      <section class="room-list">
        <div v-if="rooms.length === 0" class="empty-state">暂无公开房间，可以先创建一个。</div>
        <article v-for="room in rooms" :key="room.id" class="room-row">
          <div class="room-main"><span class="room-icon"><UsersRound :size="20" /></span><div><h2>{{ room.name }}</h2><p>{{ timeAgo(room.created_at) }}</p></div></div>
          <div class="room-meta">
            <span class="tag">{{ room.rule_set === "renju" ? "有禁手" : "无禁手" }}</span>
            <span class="tag">步时 {{ room.move_time_seconds }} 秒</span>
            <span class="tag">局时 {{ Math.round(room.total_time_seconds / 60) }} 分钟</span>
            <span class="tag"><Lock v-if="room.has_password" :size="14" /><Unlock v-else :size="14" />{{ room.has_password ? "需密码" : "无密码" }}</span>
            <span class="tag">玩家 {{ room.players }}/{{ room.max_players }}</span>
            <span class="tag">观众 {{ room.spectators_count }}/{{ room.max_spectators }}</span>
          </div>
          <button class="secondary-button" :disabled="roomFull(room)" type="button" @click="enter(room)">{{ enterLabel(room) }}</button>
        </article>
      </section>
    </template>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
    <Modal v-if="createOpen" title="创建房间" @close="createOpen = false">
      <form class="modal-form" @submit.prevent="create">
        <p v-if="createError" class="form-error">{{ createError }}</p>
        <label>房间名<input v-model="form.name" /></label>
        <label>规则<select v-model="form.rule_set"><option value="standard">无禁手</option><option value="renju">有禁手</option></select></label>
        <div class="form-subtitle">计时设置</div>
        <label>每步限时<select v-model.number="form.move_time_seconds"><option :value="15">15 秒</option><option :value="30">30 秒</option><option :value="60">60 秒</option><option :value="120">120 秒</option></select></label>
        <label>每方局时<select v-model.number="form.total_time_minutes"><option :value="5">5 分钟</option><option :value="10">10 分钟</option><option :value="15">15 分钟</option><option :value="30">30 分钟</option></select></label>
        <label class="checkbox-row"><input v-model="form.has_password" type="checkbox" />设置密码</label>
        <label v-if="form.has_password">密码<input v-model="form.password" type="password" /></label>
        <button class="primary-button" type="submit">创建并进入</button>
      </form>
    </Modal>
    <Modal v-if="joinRoom" title="输入房间密码" @close="joinRoom = null">
      <form class="modal-form" @submit.prevent="submitJoin">
        <p v-if="joinError" class="form-error">{{ joinError }}</p>
        <label>密码<input v-model="password" type="password" /></label>
        <button class="primary-button" type="submit">确认进入</button>
      </form>
    </Modal>
  </main>
</template>
