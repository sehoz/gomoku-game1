<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { BadgeCheck, ChevronLeft, ChevronRight, Clock3, LogIn, LogOut, RotateCcw, Save, Trash2, Trophy, Upload } from "lucide-vue-next";
import { api } from "../api";
import AuthModal from "../components/AuthModal.vue";
import Avatar from "../components/Avatar.vue";
import GameBoard from "../components/GameBoard.vue";
import Modal from "../components/Modal.vue";
import { authState, changePassword, isAuthenticated, logout, updateProfile } from "../stores/auth";
import type { MatchRecord, MatchReplay } from "../types";

const authOpen = ref(false);
const records = ref<MatchRecord[]>([]);
const historyError = ref("");
const historyPage = ref(1);
const historyTotalPages = ref(1);
const historyTotal = ref(0);
const replay = ref<MatchReplay | null>(null);
const replayStep = ref(0);
const replayError = ref("");
const profileForm = ref({ username: "" });
const passwordForm = ref({ oldPassword: "", newPassword: "", confirmPassword: "" });
const profileMessage = ref("");
const passwordMessage = ref("");
const avatarPreview = ref("");
const replayStones = computed(() => replay.value?.moves.slice(0, replayStep.value) || []);

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

async function loadHistory(page = historyPage.value) {
  if (!isAuthenticated()) return;
  profileForm.value.username = authState.user?.username || "";
  avatarPreview.value = authState.user?.avatar_url || "";
  try {
    const data = await api.matchHistory(page);
    records.value = data.records;
    historyPage.value = data.page;
    historyTotalPages.value = data.total_pages;
    historyTotal.value = data.total;
  } catch (err) {
    historyError.value = err instanceof Error ? err.message : "对局记录加载失败";
  }
}

function changeHistoryPage(nextPage: number) {
  if (nextPage < 1 || nextPage > historyTotalPages.value) return;
  void loadHistory(nextPage);
}

function readAvatar(event: Event) {
  const input = event.target as HTMLInputElement | null;
  const file = input?.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    profileMessage.value = "请选择图片文件。";
    return;
  }
  if (file.size > 512 * 1024) {
    profileMessage.value = "头像文件不能超过 512KB。";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    avatarPreview.value = String(reader.result || "");
  };
  reader.readAsDataURL(file);
}

async function submitProfile() {
  if (!isAuthenticated()) return;
  profileMessage.value = "";
  try {
    await updateProfile({ username: profileForm.value.username.trim(), avatar_url: avatarPreview.value });
    profileMessage.value = "个人资料已更新。";
  } catch (err) {
    profileMessage.value = err instanceof Error ? err.message : "资料更新失败";
  }
}

async function submitPassword() {
  passwordMessage.value = "";
  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    passwordMessage.value = "两次输入的新密码不一致。";
    return;
  }
  try {
    await changePassword(passwordForm.value.oldPassword, passwordForm.value.newPassword, passwordForm.value.confirmPassword);
    passwordForm.value = { oldPassword: "", newPassword: "", confirmPassword: "" };
    passwordMessage.value = "密码已修改。";
  } catch (err) {
    passwordMessage.value = err instanceof Error ? err.message : "密码修改失败";
  }
}

async function openReplay(record: MatchRecord) {
  replayError.value = "";
  try {
    replay.value = await api.matchReplay(record.id);
    replayStep.value = 0;
  } catch (err) {
    replayError.value = err instanceof Error ? err.message : "棋谱加载失败";
  }
}

async function hideRecord(record: MatchRecord) {
  if (!window.confirm("确定要从个人中心隐藏这条对局记录吗？棋谱数据不会从服务器删除。")) return;
  historyError.value = "";
  try {
    await api.hideMatchRecord(record.id);
    const nextPage = records.value.length === 1 && historyPage.value > 1 ? historyPage.value - 1 : historyPage.value;
    await loadHistory(nextPage);
  } catch (err) {
    historyError.value = err instanceof Error ? err.message : "隐藏对局记录失败";
  }
}

function setReplayStep(step: number) {
  if (!replay.value) return;
  replayStep.value = Math.max(0, Math.min(replay.value.moves.length, step));
}

function onReplaySlider(event: Event) {
  const target = event.target as HTMLInputElement | null;
  setReplayStep(Number(target?.value || 0));
}

onMounted(loadHistory);
watch(
  () => authState.user?.id,
  () => {
    profileForm.value.username = authState.user?.username || "";
    avatarPreview.value = authState.user?.avatar_url || "";
    historyPage.value = 1;
    void loadHistory(1);
  },
);
</script>

<template>
  <main class="page-shell">
    <header class="page-header"><div><RouterLink class="back-link" to="/">‹ 返回首页</RouterLink><h1>个人信息</h1><p>{{ isAuthenticated() ? "账号资料和对局统计。" : "当前为游客状态。" }}</p></div></header>
    <section class="profile-layout">
      <div class="profile-card">
        <Avatar :username="authState.user?.username || '游客'" :avatar-url="authState.user?.avatar_url" size="lg" />
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
        <div class="section-title-row"><div><h2>账号设置</h2><p>修改头像、用户名和登录密码。</p></div><BadgeCheck :size="22" /></div>
        <form class="settings-form" @submit.prevent="submitProfile">
          <div class="profile-edit-row">
            <Avatar :username="profileForm.username || authState.user?.username || '用户'" :avatar-url="avatarPreview" size="lg" />
            <label class="upload-button"><Upload :size="18" />上传头像<input accept="image/*" type="file" @change="readAvatar" /></label>
          </div>
          <label>用户名<input v-model="profileForm.username" autocomplete="username" /></label>
          <p v-if="profileMessage" class="form-error">{{ profileMessage }}</p>
          <button class="primary-button" type="submit"><Save :size="18" />保存资料</button>
        </form>
        <form class="settings-form" @submit.prevent="submitPassword">
          <label>原密码<input v-model="passwordForm.oldPassword" autocomplete="current-password" type="password" /></label>
          <label>新密码<input v-model="passwordForm.newPassword" autocomplete="new-password" type="password" /></label>
          <label>确认新密码<input v-model="passwordForm.confirmPassword" autocomplete="new-password" type="password" /></label>
          <p v-if="passwordMessage" class="form-error">{{ passwordMessage }}</p>
          <button class="secondary-button" type="submit">修改密码</button>
        </form>
      </section>
      <section v-if="isAuthenticated()" class="history-panel">
        <div class="section-title-row"><div><h2>近期对局</h2><p>记录每局开始、结束、对手和结果。</p></div><Clock3 :size="22" /></div>
        <div v-if="historyError" class="game-message warning">{{ historyError }}</div>
        <div v-else-if="records.length === 0" class="empty-state">暂无已结束对局。</div>
        <div v-else class="history-list">
          <article v-for="record in records" :key="record.id" class="history-row">
            <div><strong>{{ record.room_name }}</strong><span>{{ colorLabel(record.color) }} · 对手：{{ record.opponent.username }}</span></div>
            <div><span>开始：{{ formatTime(record.started_at) }}</span><span>结束：{{ formatTime(record.ended_at) }}</span></div>
            <div class="inline-actions"><span :class="['result-badge', record.result]">{{ resultLabel(record) }}</span><button class="secondary-button" type="button" @click="openReplay(record)">查看棋谱</button><button class="secondary-button danger-button" type="button" @click="hideRecord(record)"><Trash2 :size="16" />隐藏记录</button></div>
          </article>
          <div class="pagination-row">
            <button class="secondary-button" type="button" :disabled="historyPage <= 1" @click="changeHistoryPage(historyPage - 1)"><ChevronLeft :size="16" />上一页</button>
            <span>第 {{ historyPage }} / {{ historyTotalPages }} 页，共 {{ historyTotal }} 局</span>
            <button class="secondary-button" type="button" :disabled="historyPage >= historyTotalPages" @click="changeHistoryPage(historyPage + 1)">下一页<ChevronRight :size="16" /></button>
          </div>
        </div>
      </section>
    </section>
    <div v-if="replayError" class="game-message warning">{{ replayError }}</div>
    <Modal v-if="replay" title="棋谱复盘" @close="replay = null">
      <div class="modal-form replay-panel">
        <div>
          <h2>{{ replay.room_name }}</h2>
          <p>{{ replay.black_player.username }} 执黑，{{ replay.white_player.username }} 执白。</p>
        </div>
        <div class="replay-meta">
          <span>第 {{ replayStep }} / {{ replay.moves.length }} 手</span>
          <span>结果：{{ replay.winner === "black" ? "黑棋胜" : replay.winner === "white" ? "白棋胜" : "平局" }}</span>
        </div>
        <GameBoard :stones="replayStones" :interactive="false" show-move-numbers />
        <div class="replay-controls">
          <button class="secondary-button" type="button" @click="setReplayStep(0)"><RotateCcw :size="16" />开头</button>
          <button class="secondary-button" type="button" @click="setReplayStep(replayStep - 1)"><ChevronLeft :size="16" />上一步</button>
          <button class="secondary-button" type="button" @click="setReplayStep(replayStep + 1)">下一步<ChevronRight :size="16" /></button>
          <button class="secondary-button" type="button" @click="setReplayStep(replay.moves.length)">末尾</button>
          <div class="replay-slider-row">
            <span>0</span>
            <input class="replay-slider" :value="replayStep" type="range" min="0" :max="replay.moves.length" @input="onReplaySlider" />
            <span>{{ replay.moves.length }}</span>
          </div>
        </div>
      </div>
    </Modal>
    <AuthModal v-if="authOpen" @close="authOpen = false" />
  </main>
</template>
