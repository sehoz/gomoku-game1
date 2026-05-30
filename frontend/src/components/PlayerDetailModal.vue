<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { Trophy, XCircle } from "lucide-vue-next";
import { api } from "../api";
import type { PublicUserProfile } from "../types";
import Avatar from "./Avatar.vue";
import Modal from "./Modal.vue";

const props = defineProps<{ userId: number }>();
const emit = defineEmits<{ close: [] }>();
const user = ref<PublicUserProfile | null>(null);
const error = ref("");

async function load() {
  error.value = "";
  user.value = null;
  try {
    const data = await api.playerDetail(props.userId);
    user.value = data.user;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "玩家信息加载失败";
  }
}

onMounted(load);
watch(() => props.userId, load);
</script>

<template>
  <Modal title="玩家信息" @close="emit('close')">
    <div class="modal-form">
      <div v-if="error" class="player-detail-error"><XCircle :size="18" />{{ error }}</div>
      <div v-else-if="!user" class="empty-state">正在加载玩家信息。</div>
      <div v-else class="player-detail">
        <Avatar :username="user.username" :avatar-url="user.avatar_url" size="lg" />
        <div>
          <h2>{{ user.username }}</h2>
          <p>ID：{{ user.id }}</p>
        </div>
      </div>
      <div v-if="user" class="profile-stats player-detail-stats">
        <div><Trophy :size="20" /><span>总对局</span><strong>{{ user.stats.totalGames }}</strong></div>
        <div><Trophy :size="20" /><span>胜场</span><strong>{{ user.stats.wins }}</strong></div>
        <div><Trophy :size="20" /><span>胜率</span><strong>{{ user.stats.winRate }}%</strong></div>
      </div>
    </div>
  </Modal>
</template>
