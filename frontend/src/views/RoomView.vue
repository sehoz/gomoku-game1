<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Check, LogOut, MessageSquareText, Send, Undo2, X } from "lucide-vue-next";
import { api, roomSocketUrl } from "../api";
import Avatar from "../components/Avatar.vue";
import GameBoard from "../components/GameBoard.vue";
import { authState, isAuthenticated } from "../stores/auth";
import { playStoneSound } from "../stores/settings";
import { nextTurn } from "../rules";
import type { ChatMessage, Move, Room, RoomState, StoneColor } from "../types";

const route = useRoute();
const router = useRouter();
const roomId = Number(route.params.id);
const room = ref<Room | null>(null);
const moves = ref<Move[]>([]);
const messages = ref<ChatMessage[]>([]);
const draft = ref("");
const notice = ref("正在加载房间。");
const undoRequest = ref<{ user_id: number; username: string; color: StoneColor } | null>(null);
const ownUndoPending = ref(false);
let socket: WebSocket | null = null;

const turn = computed(() => nextTurn(moves.value));
const myColor = computed<StoneColor | null>(() => {
  if (!room.value || !authState.user) return null;
  if (room.value.black_player === authState.user.id) return "black";
  if (room.value.white_player === authState.user.id) return "white";
  return null;
});
const canMove = computed(() => room.value?.players === 2 && room.value.status !== "finished" && myColor.value === turn.value);
const statusLabel = computed(() => {
  if (!room.value) return "加载中";
  if (room.value.winner === "black") return "黑棋获胜";
  if (room.value.winner === "white") return "白棋获胜";
  if (room.value.status === "waiting") return "等待中";
  if (room.value.status === "playing") return "进行中";
  return "已结束";
});

function applyState(state: RoomState) {
  const previousMoveCount = moves.value.length;
  room.value = state.room;
  moves.value = state.moves;
  messages.value = state.messages;
  if (state.moves.length > previousMoveCount) playStoneSound();
  if (state.room.winner) {
    notice.value = `${state.room.winner === "black" ? "黑棋" : "白棋"}获胜。`;
  } else {
    notice.value = state.room.players < 2 ? "等待另一名玩家加入。" : `轮到${turn.value === "black" ? "黑棋" : "白棋"}。`;
  }
}

async function load() {
  if (!isAuthenticated()) {
    router.push("/rooms");
    return;
  }
  try {
    applyState(await api.roomState(roomId));
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "房间加载失败";
    router.push("/rooms");
    return;
  }
  socket = new WebSocket(roomSocketUrl(roomId));
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "state") applyState(data.state);
    if (data.type === "error") notice.value = data.detail;
    if (data.type === "undo_request") {
      if (data.request.user_id === authState.user?.id) {
        ownUndoPending.value = true;
        notice.value = "悔棋申请已发送，等待对方处理。";
      } else {
        undoRequest.value = data.request;
        notice.value = `${data.request.username} 申请悔棋。`;
      }
    }
    if (data.type === "undo_result") {
      ownUndoPending.value = false;
      undoRequest.value = null;
      notice.value = data.detail;
    }
    if (data.type === "closed") {
      notice.value = "房间已解散。";
      router.push("/rooms");
    }
  };
  socket.onclose = () => {
    notice.value = "连接已断开，可刷新房间重连。";
  };
}

function sendSocket(payload: object) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(payload));
  return true;
}

async function play(x: number, y: number) {
  if (!canMove.value) return;
  if (sendSocket({ type: "move", x, y })) return;
  await api.move(roomId, x, y);
  applyState(await api.roomState(roomId));
}

async function sendChat() {
  const text = draft.value.trim();
  if (!text) return;
  if (!sendSocket({ type: "chat", text })) {
    await api.chat(roomId, text);
    applyState(await api.roomState(roomId));
  }
  draft.value = "";
}

async function switchSeat(color: StoneColor) {
  if (sendSocket({ type: "switch_seat", target_color: color })) return;
  try {
    await api.switchSeat(roomId, color);
    applyState(await api.roomState(roomId));
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "换位失败";
  }
}

function requestUndo() {
  if (!sendSocket({ type: "undo_request" })) {
    notice.value = "连接已断开，暂时不能申请悔棋。";
  }
}

function acceptUndo() {
  if (!sendSocket({ type: "undo_accept" })) {
    notice.value = "连接已断开，暂时不能处理悔棋申请。";
  }
}

function rejectUndo() {
  if (!sendSocket({ type: "undo_reject" })) {
    notice.value = "连接已断开，暂时不能处理悔棋申请。";
    return;
  }
  undoRequest.value = null;
}

async function leave() {
  if (sendSocket({ type: "leave" })) {
    window.setTimeout(() => {
      socket?.close();
      router.push("/rooms");
    }, 120);
    return;
  }
  try {
    await api.leaveRoom(roomId);
  } finally {
    router.push("/rooms");
  }
}

onMounted(load);
onUnmounted(() => socket?.close());
</script>

<template>
  <main class="page-shell">
    <header class="page-header"><div><button class="link-button" type="button" @click="leave">‹ 返回房间</button><h1>{{ room?.name || "房间" }}</h1><p>黑棋在上，白棋在下；两人就位后开始。</p></div><div class="header-actions"><button class="secondary-button" :disabled="!myColor || ownUndoPending" type="button" @click="requestUndo"><Undo2 :size="18" />{{ ownUndoPending ? "等待回应" : "申请悔棋" }}</button><button class="secondary-button" type="button" @click="leave"><LogOut :size="18" />离开房间</button></div></header>
    <section class="game-layout">
      <div class="board-panel">
        <div class="board-toolbar">
          <div><span class="status-label">规则</span><strong>{{ room?.rule_set === "renju" ? "有禁手" : "无禁手" }}</strong></div>
          <div><span class="status-label">当前回合</span><strong>{{ turn === "black" ? "黑棋" : "白棋" }}</strong></div>
          <div><span class="status-label">状态</span><strong>{{ statusLabel }}</strong></div>
        </div>
        <GameBoard :stones="moves" :interactive="canMove" @play="play" />
        <div class="game-message">{{ notice }}</div>
        <div v-if="undoRequest" class="undo-request-panel">
          <strong>{{ undoRequest.username }} 申请悔棋</strong>
          <span>同意后将按规则撤销对方上一步落子。</span>
          <div class="inline-actions">
            <button class="primary-button" type="button" @click="acceptUndo"><Check :size="16" />同意</button>
            <button class="secondary-button" type="button" @click="rejectUndo"><X :size="16" />拒绝</button>
          </div>
        </div>
      </div>
      <aside class="settings-panel">
        <h2>玩家</h2>
        <div class="seat-list">
          <div class="seat-row">
            <div class="seat-player"><Avatar :username="room?.black_player_name || '等待'" /><div><strong>{{ room?.black_player_name || "等待好友加入" }}</strong><span class="seat-badge seat-badge-black">黑棋</span></div></div>
            <button v-if="myColor && !room?.black_player && room?.players === 1" class="secondary-button" @click="switchSeat('black')">换到黑棋</button>
          </div>
          <div class="seat-row">
            <div class="seat-player"><Avatar :username="room?.white_player_name || '等待'" /><div><strong>{{ room?.white_player_name || "等待好友加入" }}</strong><span class="seat-badge seat-badge-white">白棋</span></div></div>
            <button v-if="myColor && !room?.white_player && room?.players === 1" class="secondary-button" @click="switchSeat('white')">换到白棋</button>
          </div>
        </div>
        <div class="room-chat">
          <div class="chat-title"><MessageSquareText :size="18" />房间聊天</div>
          <div class="chat-messages"><p v-for="message in messages" :key="message.id">{{ message.sender_name }}：{{ message.text }}</p></div>
          <form class="chat-form" @submit.prevent="sendChat"><input v-model="draft" placeholder="输入聊天内容" /><button class="primary-button" type="submit"><Send :size="16" /></button></form>
        </div>
      </aside>
    </section>
  </main>
</template>
