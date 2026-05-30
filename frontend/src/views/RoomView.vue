<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Check, LogOut, MessageSquareText, Send, Undo2, X } from "lucide-vue-next";
import { api, roomSocketUrl } from "../api";
import Avatar from "../components/Avatar.vue";
import GameBoard from "../components/GameBoard.vue";
import Modal from "../components/Modal.vue";
import { authState, isAuthenticated } from "../stores/auth";
import { playChatSound, playStoneSound } from "../stores/settings";
import { nextTurn } from "../rules";
import type { ChatMessage, Move, Room, RoomState, SeatSwitchRequest, StoneColor, UndoRequest } from "../types";

const route = useRoute();
const router = useRouter();
const roomId = Number(route.params.id);
const room = ref<Room | null>(null);
const moves = ref<Move[]>([]);
const messages = ref<ChatMessage[]>([]);
const draft = ref("");
const notice = ref("正在加载房间。");
const undoRequest = ref<UndoRequest | null>(null);
const seatSwitchRequest = ref<SeatSwitchRequest | null>(null);
const ownUndoPending = ref(false);
const ownSeatSwitchPending = ref(false);
const socketConnected = ref(false);
const nowTick = ref(Date.now());
let socket: WebSocket | null = null;
let heartbeatTimer: number | null = null;
let statePollTimer: number | null = null;
let reconnectTimer: number | null = null;
let clockTimer: number | null = null;
let unmounted = false;

const turn = computed(() => nextTurn(moves.value));
const myColor = computed<StoneColor | null>(() => {
  if (!room.value || !authState.user) return null;
  if (room.value.black_player === authState.user.id) return "black";
  if (room.value.white_player === authState.user.id) return "white";
  return null;
});
const spectatorSeat = computed(() => room.value?.spectators.find((seat) => seat.user === authState.user?.id) || null);
const myRoleLabel = computed(() => {
  if (myColor.value === "black") return "黑棋";
  if (myColor.value === "white") return "白棋";
  if (spectatorSeat.value) return `观众${spectatorSeat.value.seat_number}`;
  return "未入席";
});
const myReady = computed(() => (myColor.value === "black" ? room.value?.black_ready : myColor.value === "white" ? room.value?.white_ready : false));
const activeGame = computed(() => room.value?.current_game?.status === "playing");
const myUndoRemaining = computed(() => (myColor.value === "black" ? room.value?.black_undo_remaining ?? 3 : myColor.value === "white" ? room.value?.white_undo_remaining ?? 3 : 0));
const currentSeatKey = computed(() => {
  if (myColor.value) return myColor.value;
  if (spectatorSeat.value) return `spectator${spectatorSeat.value.seat_number}`;
  return "";
});
const gameStarted = computed(() => activeGame.value);
const canReady = computed(() => Boolean(myColor.value && room.value?.players === 2 && !activeGame.value && room.value?.status !== "finished"));
const canMove = computed(() => activeGame.value && myColor.value === turn.value);
const canRequestUndo = computed(() => Boolean(activeGame.value && myColor.value && !ownUndoPending.value));
const canInitiateSeatSwitch = computed(() => Boolean(currentSeatKey.value && !(myColor.value && gameStarted.value)));
const spectatorSlots = computed(() => {
  const max = room.value?.max_spectators || 0;
  return Array.from({ length: max }, (_, index) => {
    const seatNumber = index + 1;
    return {
      seatNumber,
      user: room.value?.spectators.find((seat) => seat.seat_number === seatNumber) || null,
    };
  });
});
const statusLabel = computed(() => {
  if (!room.value) return "加载中";
  if (room.value.current_game?.status === "finished") {
    if (room.value.current_game.winner === "black") return "上一局黑棋获胜";
    if (room.value.current_game.winner === "white") return "上一局白棋获胜";
    return "上一局已结束";
  }
  if (activeGame.value) return "进行中";
  if (room.value.status === "waiting") return "等待中";
  return "已结束";
});
const turnLabel = computed(() => (turn.value === "black" ? "黑棋" : "白棋"));
const myRoleColor = computed<StoneColor | null>(() => (myColor.value ? myColor.value : null));
const currentGame = computed(() => room.value?.current_game || null);
const blackTimeLeft = computed(() => timeLeftFor("black"));
const whiteTimeLeft = computed(() => timeLeftFor("white"));
const stepTimeLeft = computed(() => {
  const game = currentGame.value;
  if (!game || !activeGame.value || !game.turn_started_at) return room.value?.move_time_seconds ?? 0;
  const elapsed = Math.floor((nowTick.value - new Date(game.turn_started_at).getTime()) / 1000);
  const totalRemaining = turn.value === "black" ? game.black_time_left_seconds : game.white_time_left_seconds;
  return Math.max(0, Math.min(game.move_time_seconds, totalRemaining) - elapsed);
});

function timeLeftFor(color: StoneColor) {
  const game = currentGame.value;
  if (!game) return room.value?.total_time_seconds ?? 0;
  let remaining = color === "black" ? game.black_time_left_seconds : game.white_time_left_seconds;
  if (activeGame.value && game.turn_started_at && turn.value === color) {
    remaining -= Math.floor((nowTick.value - new Date(game.turn_started_at).getTime()) / 1000);
  }
  return Math.max(0, remaining);
}

function formatSeconds(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function playerNameChanged(before: Room | null, after: Room, color: StoneColor) {
  if (color === "black") return before?.black_player_name !== after.black_player_name;
  return before?.white_player_name !== after.white_player_name;
}

function readyChanged(before: Room | null, after: Room, color: StoneColor) {
  if (!before) return false;
  return color === "black" ? before.black_ready !== after.black_ready : before.white_ready !== after.white_ready;
}

function syncPendingRequests(nextRoom: Room) {
  const pendingUndo = nextRoom.pending_undo_request;
  if (pendingUndo) {
    if (pendingUndo.user_id === authState.user?.id) {
      ownUndoPending.value = true;
      undoRequest.value = null;
    } else {
      ownUndoPending.value = false;
      undoRequest.value = pendingUndo;
    }
  } else {
    ownUndoPending.value = false;
    undoRequest.value = null;
  }

  const pendingSwitch = nextRoom.pending_seat_switch_request;
  if (pendingSwitch) {
    if (pendingSwitch.requester_id === authState.user?.id) {
      ownSeatSwitchPending.value = true;
      seatSwitchRequest.value = null;
    } else if (pendingSwitch.target_user_id === authState.user?.id) {
      ownSeatSwitchPending.value = false;
      seatSwitchRequest.value = pendingSwitch;
    } else {
      ownSeatSwitchPending.value = false;
      seatSwitchRequest.value = null;
    }
  } else {
    ownSeatSwitchPending.value = false;
    seatSwitchRequest.value = null;
  }
}

function applyState(state: RoomState) {
  const previousMoveCount = moves.value.length;
  const previousMessageCount = messages.value.length;
  const previousRoom = room.value;
  room.value = state.room;
  moves.value = state.moves;
  messages.value = state.messages;
  if (state.moves.length > previousMoveCount) playStoneSound();
  if (previousRoom && state.messages.length > previousMessageCount) playChatSound();
  syncPendingRequests(state.room);
  if (previousRoom && playerNameChanged(previousRoom, state.room, "black") && state.room.black_player_name) {
    notice.value = `${state.room.black_player_name} 已进入黑棋位置。`;
  } else if (previousRoom && playerNameChanged(previousRoom, state.room, "white") && state.room.white_player_name) {
    notice.value = `${state.room.white_player_name} 已进入白棋位置。`;
  } else if (readyChanged(previousRoom, state.room, "black")) {
    notice.value = `黑棋${state.room.black_ready ? "已准备" : "取消准备"}。`;
  } else if (readyChanged(previousRoom, state.room, "white")) {
    notice.value = `白棋${state.room.white_ready ? "已准备" : "取消准备"}。`;
  } else if (previousRoom?.status !== "playing" && state.room.status === "playing") {
    notice.value = "双方已准备，对局开始。";
  } else if (state.room.current_game?.status === "finished") {
    if (state.room.current_game.winner) {
      notice.value = `${state.room.current_game.winner === "black" ? "黑棋" : "白棋"}获胜。本房间可继续准备下一局。`;
    } else {
      notice.value = "本局已结束。本房间可继续准备下一局。";
    }
  } else if (state.room.players < 2) {
    notice.value = "等待另一名玩家加入。";
  } else if (state.room.status === "waiting") {
    notice.value = "双方都准备后对局开始。";
  } else {
    notice.value = `轮到${turn.value === "black" ? "黑棋" : "白棋"}。`;
  }
  if (state.room.pending_undo_request && state.room.pending_undo_request.user_id !== authState.user?.id) {
    notice.value = `${state.room.pending_undo_request.username} 申请悔棋，请处理。`;
  } else if (state.room.pending_seat_switch_request && state.room.pending_seat_switch_request.target_user_id === authState.user?.id) {
    notice.value = `${state.room.pending_seat_switch_request.requester_username} 申请与你换位，请处理。`;
  }
}

async function loadState(redirectOnError = false) {
  try {
    applyState(await api.roomState(roomId));
    return true;
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "房间加载失败";
    if (redirectOnError) router.push("/rooms");
    return false;
  }
}

async function load() {
  if (!isAuthenticated()) {
    router.push("/rooms");
    return;
  }
  if (!(await loadState(true))) return;
  statePollTimer = window.setInterval(() => {
    if (!socketConnected.value) void loadState(false);
  }, 1000);
  clockTimer = window.setInterval(() => {
    nowTick.value = Date.now();
  }, 250);
  connectSocket();
}

function connectSocket() {
  if (unmounted || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket = new WebSocket(roomSocketUrl(roomId));
  socket.onopen = () => {
    socketConnected.value = true;
    sendSocket({ type: "ping" });
    heartbeatTimer = window.setInterval(() => sendSocket({ type: "ping" }), 1000);
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "state") applyState(data.state);
    if (data.type === "error") {
      ownUndoPending.value = false;
      ownSeatSwitchPending.value = false;
      notice.value = data.detail;
      void loadState(false);
    }
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
    if (data.type === "seat_switch_request") {
      if (data.request.requester_id === authState.user?.id) {
        ownSeatSwitchPending.value = true;
        notice.value = `换位申请已发送，等待 ${data.request.target_username} 处理。`;
      } else if (data.request.target_user_id === authState.user?.id) {
        seatSwitchRequest.value = data.request;
        notice.value = `${data.request.requester_username} 申请与你换位。`;
      }
    }
    if (data.type === "seat_switch_result") {
      ownSeatSwitchPending.value = false;
      seatSwitchRequest.value = null;
      notice.value = data.detail;
    }
    if (data.type === "peer_status") {
      if (data.user_id !== authState.user?.id) {
        notice.value = data.online ? `${data.username} 已重新连接。` : `${data.username} 已断开连接，等待重连。`;
      }
    }
    if (data.type === "closed") {
      notice.value = "房间已解散。";
      router.push("/rooms");
    }
  };
  socket.onclose = () => {
    socketConnected.value = false;
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (!unmounted) {
      notice.value = "实时连接已断开，正在自动重连。";
      reconnectTimer = window.setTimeout(connectSocket, 2000);
    }
  };
}

function sendSocket(payload: object) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(payload));
  return true;
}

async function play(x: number, y: number) {
  if (!canMove.value) return;
  const color = myColor.value;
  if (!color) return;
  const before = moves.value;
  moves.value = [...moves.value, { x, y, color, player: authState.user?.id }];
  playStoneSound();
  notice.value = "落子已发送。";
  if (sendSocket({ type: "move", x, y })) return;
  try {
    await api.move(roomId, x, y);
    applyState(await api.roomState(roomId));
  } catch (err) {
    moves.value = before;
    notice.value = err instanceof Error ? err.message : "落子失败";
  }
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

async function switchPosition(targetSeat: string) {
  if (!canInitiateSeatSwitch.value || targetSeat === currentSeatKey.value) return;
  if (sendSocket({ type: "switch_position", target_seat: targetSeat })) return;
  try {
    await api.switchPosition(roomId, targetSeat);
    applyState(await api.roomState(roomId));
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "换位失败";
    void loadState(false);
  }
}

function seatButtonLabel(seatKey: string, occupied: boolean) {
  if (seatKey === currentSeatKey.value) return "当前位置";
  if (ownSeatSwitchPending.value) return "等待回应";
  return occupied ? "申请换位" : "切换";
}

function canSwitchTo(seatKey: string) {
  return canInitiateSeatSwitch.value && seatKey !== currentSeatKey.value && !ownSeatSwitchPending.value;
}

async function toggleReady() {
  if (!myColor.value) return;
  const nextReady = !myReady.value;
  if (sendSocket({ type: "ready", ready: nextReady })) return;
  try {
    await api.readyRoom(roomId, nextReady);
    applyState(await api.roomState(roomId));
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "准备状态更新失败";
  }
}

function requestUndo() {
  if (!activeGame.value || !myColor.value) {
    notice.value = "当前没有进行中的对局，不能悔棋。";
    return;
  }
  if (myUndoRemaining.value <= 0) {
    notice.value = "本局悔棋次数已用完。";
    return;
  }
  if (!moves.value.some((move) => move.player === authState.user?.id)) {
    notice.value = "你还没有可以撤销的落子。";
    return;
  }
  ownUndoPending.value = true;
  notice.value = "悔棋申请已发送，等待对方处理。";
  if (sendSocket({ type: "undo_request" })) return;
  api.requestUndo(roomId)
    .then(() => loadState(false))
    .catch((err) => {
      ownUndoPending.value = false;
      notice.value = err instanceof Error ? err.message : "悔棋申请失败";
    });
}

async function respondUndo(accepted: boolean) {
  if (sendSocket({ type: accepted ? "undo_accept" : "undo_reject" })) {
    if (!accepted) undoRequest.value = null;
    return;
  }
  try {
    const result = await api.respondUndo(roomId, accepted);
    notice.value = result.detail;
    undoRequest.value = null;
    await loadState(false);
  } catch (err) {
    ownUndoPending.value = false;
    notice.value = err instanceof Error ? err.message : "处理悔棋申请失败";
  }
}

function acceptUndo() {
  void respondUndo(true);
}

function rejectUndo() {
  void respondUndo(false);
}

async function respondSeatSwitch(accepted: boolean) {
  if (sendSocket({ type: accepted ? "seat_switch_accept" : "seat_switch_reject" })) {
    if (!accepted) seatSwitchRequest.value = null;
    return;
  }
  try {
    const result = await api.respondSeatSwitch(roomId, accepted);
    notice.value = result.detail;
    seatSwitchRequest.value = null;
    await loadState(false);
  } catch (err) {
    notice.value = err instanceof Error ? err.message : "处理换位申请失败";
  }
}

function acceptSeatSwitch() {
  void respondSeatSwitch(true);
}

function rejectSeatSwitch() {
  void respondSeatSwitch(false);
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
onUnmounted(() => {
  unmounted = true;
  if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
  if (statePollTimer !== null) window.clearInterval(statePollTimer);
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  if (clockTimer !== null) window.clearInterval(clockTimer);
  socket?.close();
});
</script>

<template>
  <main class="page-shell">
    <header class="page-header"><div><button class="link-button" type="button" @click="leave">‹ 返回房间</button><h1>{{ room?.name || "房间" }}</h1><p>黑棋在上，白棋在下；两名玩家都准备后开始。</p></div><div class="header-actions"><button class="secondary-button" type="button" @click="leave"><LogOut :size="18" />离开房间</button></div></header>
    <section class="game-layout">
      <div class="board-panel">
        <div class="board-controlbar">
          <div class="control-item">
            <span class="status-label">我的位置</span>
            <strong class="stone-status">
              <span v-if="myRoleColor" :class="['stone-icon', `stone-icon-${myRoleColor}`]" />
              <span>{{ myRoleLabel }}</span>
            </strong>
          </div>
          <div class="control-item">
            <span class="status-label">当前回合</span>
            <strong class="stone-status"><span :class="['stone-icon', `stone-icon-${turn}`]" />{{ turnLabel }}</strong>
          </div>
          <div class="control-item"><span class="status-label">步时</span><strong>{{ formatSeconds(stepTimeLeft) }}</strong></div>
          <div class="control-item"><span class="status-label">状态</span><strong>{{ statusLabel }}</strong></div>
          <div class="control-actions">
            <button class="primary-button" :disabled="!canReady" type="button" @click="toggleReady"><Check :size="18" />{{ myReady ? "取消准备" : "准备" }}</button>
            <button class="secondary-button" :disabled="!activeGame || !myColor || ownUndoPending" type="button" @click="requestUndo"><Undo2 :size="18" />{{ ownUndoPending ? "等待回应" : `悔棋（${myUndoRemaining}）` }}</button>
          </div>
        </div>
        <div class="control-notice board-notice" :class="{ warning: notice.includes('失败') || notice.includes('断开') || notice.includes('不能') || notice.includes('用完') }">{{ notice }}</div>
        <GameBoard :stones="moves" :interactive="canMove" @play="play" />
      </div>
      <aside class="settings-panel">
        <h2>玩家</h2>
        <div class="seat-list">
          <div class="seat-row">
            <div class="seat-player"><Avatar :username="room?.black_player_name || '等待'" /><div><strong>{{ room?.black_player_name || "等待好友加入" }} <span class="seat-inline-label seat-badge-black">黑棋</span></strong><span class="seat-meta-line"><span :class="['ready-badge', room?.black_ready ? 'ready' : 'waiting']">{{ room?.black_ready ? "已准备" : "未准备" }}</span><span class="time-pill">{{ formatSeconds(blackTimeLeft) }}</span></span></div></div>
            <button class="secondary-button" :disabled="!canSwitchTo('black')" @click="switchPosition('black')">{{ seatButtonLabel('black', Boolean(room?.black_player)) }}</button>
          </div>
          <div class="seat-row">
            <div class="seat-player"><Avatar :username="room?.white_player_name || '等待'" /><div><strong>{{ room?.white_player_name || "等待好友加入" }} <span class="seat-inline-label seat-badge-white">白棋</span></strong><span class="seat-meta-line"><span :class="['ready-badge', room?.white_ready ? 'ready' : 'waiting']">{{ room?.white_ready ? "已准备" : "未准备" }}</span><span class="time-pill">{{ formatSeconds(whiteTimeLeft) }}</span></span></div></div>
            <button class="secondary-button" :disabled="!canSwitchTo('white')" @click="switchPosition('white')">{{ seatButtonLabel('white', Boolean(room?.white_player)) }}</button>
          </div>
        </div>
        <div class="spectator-panel">
          <h2>观战席</h2>
          <div class="spectator-list">
            <div v-for="slot in spectatorSlots" :key="slot.seatNumber" class="spectator-row">
              <div class="spectator-main"><span class="seat-badge">观众{{ slot.seatNumber }}</span><strong>{{ slot.user?.username || "空位" }}</strong></div>
              <button class="secondary-button" :disabled="!canSwitchTo(`spectator${slot.seatNumber}`)" @click="switchPosition(`spectator${slot.seatNumber}`)">{{ seatButtonLabel(`spectator${slot.seatNumber}`, Boolean(slot.user)) }}</button>
            </div>
          </div>
        </div>
        <div class="room-chat">
          <div class="chat-title"><MessageSquareText :size="18" />房间聊天</div>
          <div class="chat-messages"><p v-for="message in messages" :key="message.id">{{ message.sender_name }}：{{ message.text }}</p></div>
          <form class="chat-form" @submit.prevent="sendChat"><input v-model="draft" placeholder="输入聊天内容" /><button class="primary-button" type="submit"><Send :size="16" /></button></form>
        </div>
      </aside>
    </section>
    <Modal v-if="undoRequest" title="悔棋申请" @close="rejectUndo">
      <div class="modal-form">
        <p><strong>{{ undoRequest.username }}</strong> 申请悔棋。同意后将按规则撤销对方上一步落子。</p>
        <div class="inline-actions">
          <button class="primary-button" type="button" @click="acceptUndo"><Check :size="16" />同意</button>
          <button class="secondary-button" type="button" @click="rejectUndo"><X :size="16" />拒绝</button>
        </div>
      </div>
    </Modal>
    <Modal v-if="seatSwitchRequest" title="换位申请" @close="rejectSeatSwitch">
      <div class="modal-form">
        <p><strong>{{ seatSwitchRequest.requester_username }}</strong> 想从{{ seatSwitchRequest.from_label }}换到你的{{ seatSwitchRequest.target_label }}位置。</p>
        <div class="inline-actions">
          <button class="primary-button" type="button" @click="acceptSeatSwitch"><Check :size="16" />同意</button>
          <button class="secondary-button" type="button" @click="rejectSeatSwitch"><X :size="16" />拒绝</button>
        </div>
      </div>
    </Modal>
  </main>
</template>
