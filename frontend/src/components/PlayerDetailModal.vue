<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { Clock3, Trophy, XCircle } from "lucide-vue-next";
import { api } from "../api";
import type { MatchRecord, PublicUserProfile } from "../types";
import Avatar from "./Avatar.vue";
import Modal from "./Modal.vue";

const props = defineProps<{ userId: number }>();
const emit = defineEmits<{ close: [] }>();
const user = ref<PublicUserProfile | null>(null);
const error = ref("");
const avatarPreviewOpen = ref(false);

async function load() {
  error.value = "";
  user.value = null;
  avatarPreviewOpen.value = false;
  try {
    const data = await api.playerDetail(props.userId);
    user.value = data.user;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "玩家信息加载失败";
  }
}

function resultLabel(record: MatchRecord) {
  if (record.result === "win") return "胜";
  if (record.result === "loss") return "负";
  if (record.result === "draw") return "平";
  return "未完成";
}

function colorLabel(color: string) {
  return color === "black" ? "黑棋" : "白棋";
}

function formatDate(value: string | null) {
  if (!value) return "未记录";
  return new Date(value).toLocaleDateString();
}

function openAvatarPreview() {
  if (user.value?.avatar_url) avatarPreviewOpen.value = true;
}

onMounted(load);
watch(() => props.userId, load);
</script>

<template>
  <Modal title="玩家信息" @close="emit('close')">
    <div class="modal-form">
      <div v-if="error" class="player-detail-error"><XCircle :size="18" />{{ error }}</div>
      <div v-else-if="!user" class="empty-state">正在加载玩家信息。</div>
      <template v-else>
        <div class="player-detail">
          <button class="avatar-large-button" :disabled="!user.avatar_url" type="button" title="查看头像原图" @click="openAvatarPreview">
            <Avatar :username="user.username" :avatar-url="user.avatar_url" size="lg" />
          </button>
          <div>
            <h2>{{ user.username }}</h2>
            <p>ID：{{ user.id }}</p>
          </div>
        </div>
        <div class="profile-stats player-detail-stats">
          <div><Trophy :size="20" /><span>总对局</span><strong>{{ user.stats.totalGames }}</strong></div>
          <div><Trophy :size="20" /><span>胜场</span><strong>{{ user.stats.wins }}</strong></div>
          <div><Trophy :size="20" /><span>胜率</span><strong>{{ user.stats.winRate }}%</strong></div>
        </div>
        <div class="player-recent">
          <div class="section-title-row"><div><h2>近期对局</h2><p>最近五局公开记录。</p></div><Clock3 :size="20" /></div>
          <div v-if="user.recent_matches.length === 0" class="empty-state">暂无近期对局。</div>
          <template v-else>
            <article v-for="record in user.recent_matches" :key="record.id" class="player-recent-row">
              <div><strong>{{ record.room_name }}</strong><span>{{ colorLabel(record.color) }} · 对手：{{ record.opponent.username }}</span></div>
              <div><span>{{ formatDate(record.ended_at || record.started_at) }}</span><span :class="['result-badge', record.result]">{{ resultLabel(record) }}</span></div>
            </article>
          </template>
        </div>
      </template>
      <div v-if="avatarPreviewOpen && user?.avatar_url" class="avatar-preview-backdrop" @click="avatarPreviewOpen = false">
        <img :src="user.avatar_url" :alt="`${user.username} 头像原图`" />
      </div>
    </div>
  </Modal>
</template>
