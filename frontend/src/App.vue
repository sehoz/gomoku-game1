<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "./api";
import GlobalSettings from "./components/GlobalSettings.vue";
import Modal from "./components/Modal.vue";
import { authState, initAuth } from "./stores/auth";
import { connectPresence } from "./stores/presence";
import type { RoomInvitation } from "./types";

const router = useRouter();
const invitations = ref<RoomInvitation[]>([]);
let invitationTimer: number | null = null;

async function refreshInvitations() {
  if (!authState.user) {
    invitations.value = [];
    return;
  }
  try {
    const data = await api.invitations();
    invitations.value = data.invitations;
  } catch {
    invitations.value = [];
  }
}

function startInvitationPolling() {
  if (invitationTimer !== null) return;
  void refreshInvitations();
  invitationTimer = window.setInterval(refreshInvitations, 1000);
}

function stopInvitationPolling() {
  if (invitationTimer !== null) window.clearInterval(invitationTimer);
  invitationTimer = null;
  invitations.value = [];
}

async function respondInvitation(invitation: RoomInvitation, accepted: boolean) {
  try {
    const data = await api.respondInvitation(invitation.id, accepted);
    invitations.value = invitations.value.filter((item) => item.id !== invitation.id);
    if (accepted && data.room) router.push(`/rooms/${data.room.id}`);
  } catch {
    invitations.value = invitations.value.filter((item) => item.id !== invitation.id);
  }
}

initAuth();
connectPresence();
watch(
  () => authState.user?.id,
  (userId) => {
    connectPresence();
    if (userId) startInvitationPolling();
    else stopInvitationPolling();
  },
);
onUnmounted(stopInvitationPolling);
</script>

<template>
  <RouterView />
  <GlobalSettings />
  <Modal v-if="invitations.length" title="房间邀请" @close="respondInvitation(invitations[0], false)">
    <div class="modal-form">
      <p><strong>{{ invitations[0].inviter_username }}</strong> 邀请你加入房间：{{ invitations[0].room_name }}</p>
      <div class="inline-actions">
        <button class="primary-button" type="button" @click="respondInvitation(invitations[0], true)">接受</button>
        <button class="secondary-button" type="button" @click="respondInvitation(invitations[0], false)">拒绝</button>
      </div>
    </div>
  </Modal>
</template>
