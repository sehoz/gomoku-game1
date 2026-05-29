<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Lock, Plus, Unlock, UsersRound } from "lucide-vue-next";
import { api } from "../api";
import AuthModal from "../components/AuthModal.vue";
import Modal from "../components/Modal.vue";
import { isAuthenticated } from "../stores/auth";
import type { Room, RuleSet } from "../types";

const router = useRouter();
const rooms = ref<Room[]>([]);
const error = ref("");
const authOpen = ref(false);
const createOpen = ref(false);
const joinRoom = ref<Room | null>(null);
const password = ref("");
const form = ref({ name: "好友对局", rule_set: "standard" as RuleSet, has_password: false, password: "" });

async function load() {
  if (!isAuthenticated()) return;
  try {
    rooms.value = await api.rooms();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "房间列表加载失败";
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
  try {
    const next = await api.joinRoom(joinRoom.value.id, password.value);
    router.push(`/rooms/${next.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加入失败";
  }
}

async function create() {
  try {
    const room = await api.createRoom(form.value);
    router.push(`/rooms/${room.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "创建失败";
  }
}

onMounted(load);
</script>

<template>
  <main class="page-shell">
    <header class="page-header">
      <div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>联机对战</h1><p>登录后可以创建或加入房间。</p></div>
      <button v-if="isAuthenticated()" class="primary-button" type="button" @click="createOpen = true"><Plus :size="18" />创建房间</button>
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
            <span class="tag"><Lock v-if="room.has_password" :size="14" /><Unlock v-else :size="14" />{{ room.has_password ? "需密码" : "无密码" }}</span>
            <span class="tag">{{ room.players }}/{{ room.max_players }}</span>
          </div>
          <button class="secondary-button" :disabled="room.players >= room.max_players" type="button" @click="enter(room)">{{ room.players >= room.max_players ? "已满" : "进入" }}</button>
        </article>
      </section>
    </template>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
    <Modal v-if="createOpen" title="创建房间" @close="createOpen = false">
      <form class="modal-form" @submit.prevent="create">
        <label>房间名<input v-model="form.name" /></label>
        <label>规则<select v-model="form.rule_set"><option value="standard">无禁手</option><option value="renju">有禁手</option></select></label>
        <label class="checkbox-row"><input v-model="form.has_password" type="checkbox" />设置密码</label>
        <label v-if="form.has_password">密码<input v-model="form.password" type="password" /></label>
        <button class="primary-button" type="submit">创建并进入</button>
      </form>
    </Modal>
    <Modal v-if="joinRoom" title="输入房间密码" @close="joinRoom = null">
      <form class="modal-form" @submit.prevent="submitJoin">
        <label>密码<input v-model="password" type="password" /></label>
        <button class="primary-button" type="submit">确认进入</button>
      </form>
    </Modal>
  </main>
</template>
