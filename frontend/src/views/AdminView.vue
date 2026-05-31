<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { LogOut, RefreshCw, Save, Shield, Trash2, UserPlus } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { api } from "../api";
import { authState, logout } from "../stores/auth";
import type { AdminRoom, AdminMatch, AdminUser } from "../types";

const router = useRouter();
const users = ref<AdminUser[]>([]);
const rooms = ref<AdminRoom[]>([]);
const matches = ref<AdminMatch[]>([]);
const message = ref("");
const loading = ref(false);
const selectedUsers = ref<number[]>([]);
const selectedRooms = ref<number[]>([]);
const selectedMatches = ref<number[]>([]);
const newUser = ref({ username: "", password: "gomoku123", email: "", is_staff: false, is_superuser: false, is_active: true });

const canUseAdmin = computed(() => Boolean(authState.user?.is_admin));

function formatTime(value: string) {
  return new Date(value).toLocaleString();
}

function formatOptionalTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "未记录";
}

function ruleLabel(rule: string) {
  return rule === "renju" ? "有禁手" : "无禁手";
}

function winnerLabel(winner: string) {
  if (winner === "black") return "黑棋胜";
  if (winner === "white") return "白棋胜";
  return "无胜者";
}

async function loadAdminData() {
  if (!authState.ready) return;
  if (!canUseAdmin.value) {
    router.replace("/");
    return;
  }
  loading.value = true;
  try {
    const [userData, roomData, matchData] = await Promise.all([api.adminUsers(), api.adminRooms(), api.adminMatches()]);
    users.value = userData.users;
    rooms.value = roomData.rooms;
    matches.value = matchData.matches;
    message.value = "";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "后台数据加载失败";
  } finally {
    loading.value = false;
  }
}

async function createUser() {
  try {
    const data = await api.adminCreateUser(newUser.value);
    users.value = [...users.value, data.user];
    newUser.value = { username: "", password: "gomoku123", email: "", is_staff: false, is_superuser: false, is_active: true };
    message.value = "用户已创建。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "创建用户失败";
  }
}

async function saveUser(user: AdminUser) {
  try {
    const data = await api.adminUpdateUser(user.id, user);
    users.value = users.value.map((item) => (item.id === user.id ? data.user : item));
    message.value = "用户信息已保存。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "保存用户失败";
  }
}

async function deleteUser(userId: number) {
  try {
    await api.adminDeleteUser(userId);
    users.value = users.value.filter((user) => user.id !== userId);
    selectedUsers.value = selectedUsers.value.filter((id) => id !== userId);
    message.value = "用户已删除。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "删除用户失败";
  }
}

async function deleteSelectedUsers() {
  for (const id of [...selectedUsers.value]) {
    await deleteUser(id);
  }
}

async function saveRoom(room: AdminRoom) {
  try {
    const data = await api.adminUpdateRoom(room.id, room);
    rooms.value = rooms.value.map((item) => (item.id === room.id ? data.room : item));
    message.value = "房间信息已保存。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "保存房间失败";
  }
}

async function deleteRoom(roomId: number) {
  try {
    await api.adminDeleteRoom(roomId);
    rooms.value = rooms.value.filter((room) => room.id !== roomId);
    selectedRooms.value = selectedRooms.value.filter((id) => id !== roomId);
    message.value = "房间已删除。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "删除房间失败";
  }
}

async function deleteSelectedRooms() {
  for (const id of [...selectedRooms.value]) {
    await deleteRoom(id);
  }
}

async function deleteMatch(matchId: number) {
  if (!window.confirm("确定要从数据库永久删除这条对局记录吗？棋谱和隐藏记录也会一起删除。")) return;
  try {
    await api.adminDeleteMatch(matchId);
    matches.value = matches.value.filter((match) => match.id !== matchId);
    selectedMatches.value = selectedMatches.value.filter((id) => id !== matchId);
    message.value = "对局记录已永久删除。";
  } catch (err) {
    message.value = err instanceof Error ? err.message : "删除对局记录失败";
  }
}

async function deleteSelectedMatches() {
  if (!window.confirm("确定要从数据库永久删除选中的对局记录吗？")) return;
  for (const id of [...selectedMatches.value]) {
    try {
      await api.adminDeleteMatch(id);
      matches.value = matches.value.filter((match) => match.id !== id);
      selectedMatches.value = selectedMatches.value.filter((matchId) => matchId !== id);
      message.value = "选中的对局记录已永久删除。";
    } catch (err) {
      message.value = err instanceof Error ? err.message : "删除对局记录失败";
      break;
    }
  }
}

async function adminLogout() {
  await logout();
  router.replace("/");
}

onMounted(loadAdminData);
watch(() => authState.ready, () => loadAdminData());
</script>

<template>
  <main class="page-shell admin-page">
    <header class="page-header">
      <div><p class="eyebrow">Admin</p><h1>后台管理</h1><p>管理员账号只用于维护用户和房间数据。</p></div>
      <div class="header-actions">
        <button class="secondary-button" type="button" @click="loadAdminData"><RefreshCw :size="18" :class="{ spinning: loading }" />刷新</button>
        <button class="secondary-button" type="button" @click="adminLogout"><LogOut :size="18" />退出</button>
      </div>
    </header>
    <div v-if="message" class="game-message" :class="{ warning: message.includes('失败') || message.includes('不能') }">{{ message }}</div>

    <section class="admin-panel">
      <div class="section-title-row"><div><h2>用户管理</h2><p>创建、编辑、禁用或删除账号。</p></div><Shield :size="22" /></div>
      <form class="admin-create-row" @submit.prevent="createUser">
        <input v-model="newUser.username" placeholder="用户名" />
        <input v-model="newUser.password" placeholder="初始密码" type="password" />
        <input v-model="newUser.email" placeholder="邮箱，可空" />
        <label class="checkbox-row"><input v-model="newUser.is_active" type="checkbox" />启用</label>
        <label class="checkbox-row"><input v-model="newUser.is_staff" type="checkbox" />管理员</label>
        <button class="primary-button" type="submit"><UserPlus :size="18" />新增用户</button>
      </form>
      <div class="admin-actions"><button class="secondary-button danger-button" :disabled="selectedUsers.length === 0" type="button" @click="deleteSelectedUsers"><Trash2 :size="18" />删除选中</button></div>
      <div class="admin-table">
        <div class="admin-row admin-row-head"><span></span><span>ID</span><span>用户名</span><span>邮箱</span><span>状态</span><span>权限</span><span>加入时间</span><span>操作</span></div>
        <div v-for="user in users" :key="user.id" class="admin-row">
          <input v-model="selectedUsers" :value="user.id" type="checkbox" />
          <span>{{ user.id }}</span>
          <input v-model="user.username" />
          <input v-model="user.email" />
          <label class="checkbox-row"><input v-model="user.is_active" type="checkbox" />启用</label>
          <label class="checkbox-row"><input v-model="user.is_staff" type="checkbox" />管理员</label>
          <span>{{ formatTime(user.date_joined) }}</span>
          <div class="inline-actions"><button class="secondary-button" type="button" @click="saveUser(user)"><Save :size="16" />保存</button><button class="secondary-button danger-button" type="button" @click="deleteUser(user.id)"><Trash2 :size="16" /></button></div>
        </div>
      </div>
    </section>

    <section class="admin-panel">
      <div class="section-title-row"><div><h2>房间管理</h2><p>查看、编辑或删除当前房间。</p></div><Shield :size="22" /></div>
      <div class="admin-actions"><button class="secondary-button danger-button" :disabled="selectedRooms.length === 0" type="button" @click="deleteSelectedRooms"><Trash2 :size="18" />删除选中</button></div>
      <div class="admin-table">
        <div class="admin-row admin-room-row admin-row-head"><span></span><span>ID</span><span>房间名</span><span>规则</span><span>状态</span><span>玩家</span><span>房主</span><span>操作</span></div>
        <div v-for="room in rooms" :key="room.id" class="admin-row admin-room-row">
          <input v-model="selectedRooms" :value="room.id" type="checkbox" />
          <span>{{ room.id }}</span>
          <input v-model="room.name" />
          <select v-model="room.rule_set"><option value="standard">无禁手</option><option value="renju">有禁手</option></select>
          <select v-model="room.status"><option value="waiting">等待中</option><option value="playing">进行中</option><option value="finished">已结束</option></select>
          <span>{{ room.black_player_name || "空" }} / {{ room.white_player_name || "空" }} · 观众 {{ room.spectators_count }}</span>
          <span>{{ room.host_name || "无" }}</span>
          <div class="inline-actions"><button class="secondary-button" type="button" @click="saveRoom(room)"><Save :size="16" />保存</button><button class="secondary-button danger-button" type="button" @click="deleteRoom(room.id)"><Trash2 :size="16" /></button></div>
        </div>
      </div>
    </section>

    <section class="admin-panel">
      <div class="section-title-row"><div><h2>对局记录管理</h2><p>这里只展示已结束对局；删除会从数据库永久移除棋谱和相关隐藏记录。</p></div><Shield :size="22" /></div>
      <div class="admin-actions"><button class="secondary-button danger-button" :disabled="selectedMatches.length === 0" type="button" @click="deleteSelectedMatches"><Trash2 :size="18" />永久删除选中</button></div>
      <div class="admin-table">
        <div class="admin-row admin-match-row admin-row-head"><span></span><span>ID</span><span>房间</span><span>玩家</span><span>规则</span><span>结果</span><span>手数</span><span>开始 / 结束</span><span>操作</span></div>
        <div v-for="match in matches" :key="match.id" class="admin-row admin-match-row">
          <input v-model="selectedMatches" :value="match.id" type="checkbox" />
          <span>{{ match.id }}</span>
          <strong>{{ match.room_name || "未知房间" }}</strong>
          <span>黑：{{ match.black_player_name || "未知" }} / 白：{{ match.white_player_name || "未知" }}</span>
          <span>{{ ruleLabel(match.rule_set) }}</span>
          <span>{{ winnerLabel(match.winner) }} · {{ match.end_reason || "正常结束" }}</span>
          <span>{{ match.moves_count }}</span>
          <span>{{ formatOptionalTime(match.started_at) }} / {{ formatOptionalTime(match.ended_at) }}</span>
          <div class="inline-actions"><button class="secondary-button danger-button" type="button" @click="deleteMatch(match.id)"><Trash2 :size="16" />永久删除</button></div>
        </div>
        <div v-if="matches.length === 0" class="empty-state">暂无已结束对局记录。</div>
      </div>
    </section>
  </main>
</template>
