<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Check, MessageSquareText, Send, Settings2, Undo2, X } from "lucide-vue-next";
import { api, roomSocketUrl } from "../api";
import Avatar from "../components/Avatar.vue";
import GameBoard from "../components/GameBoard.vue";
import Modal from "../components/Modal.vue";
import PlayerDetailModal from "../components/PlayerDetailModal.vue";
import { authState, isAuthenticated } from "../stores/auth";
import { presenceState } from "../stores/presence";
import { playChatSound, playGameEndSound, playGameStartSound, playStoneSound } from "../stores/settings";
import { nextTurn } from "../rules";
import type { ChatMessage, Move, Room, RoomState, RuleSet, SeatSwitchRequest, StoneColor, UndoRequest } from "../types";

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
const pendingOptimisticMoves = ref<Move[]>([]);
const sentInviteLabels = ref<Record<number, string>>({});
const socketConnected = ref(false);
const nowTick = ref(Date.now());
const selectedPlayerId = ref<number | null>(null);
const gameFeedback = ref<{ kind: "start" | "end"; title: string; detail: string } | null>(null);
const roomSettingsOpen = ref(false);
const roomSettingsError = ref("");
const roomSettingsForm = ref({
  name: "",
  rule_set: "standard" as RuleSet,
  has_password: false,
  password: "",
  move_time_seconds: 30,
  total_time_minutes: 10,
});
let socket: WebSocket | null = null;
let heartbeatTimer: number | null = null;
let statePollTimer: number | null = null;
let reconnectTimer: number | null = null;
let clockTimer: number | null = null;
let feedbackTimer: number | null = null;
let unmounted = false;
let stateLoadInFlight = false;

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
const isHost = computed(() => Boolean(room.value?.host && room.value.host === authState.user?.id));
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
const roomUserIds = computed(() => {
  const ids = new Set<number>();
  if (room.value?.black_player) ids.add(room.value.black_player);
  if (room.value?.white_player) ids.add(room.value.white_player);
  room.value?.spectators.forEach((seat) => ids.add(seat.user));
  return ids;
});
const inviteCandidates = computed(() => presenceState.users.filter((user) => user.id !== authState.user?.id && !roomUserIds.value.has(user.id)));
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
  if (!game || !activeGame.value || !game.turn_started_at) {
    const limit = room.value?.move_time_seconds ?? 0;
    return limit > 0 ? limit : -1;
  }
  const elapsed = Math.floor((nowTick.value - new Date(game.turn_started_at).getTime()) / 1000);
  const totalRemaining = turn.value === "black" ? game.black_time_left_seconds : game.white_time_left_seconds;
  const moveLeft = game.move_time_seconds > 0 ? game.move_time_seconds - elapsed : Number.POSITIVE_INFINITY;
  const totalLeft = game.total_time_seconds > 0 ? totalRemaining - elapsed : Number.POSITIVE_INFINITY;
  const value = Math.min(moveLeft, totalLeft);
  return Number.isFinite(value) ? Math.max(0, value) : -1;
});

function timeLeftFor(color: StoneColor) {
  const game = currentGame.value;
  if (!game || !activeGame.value) {
    const limit = room.value?.total_time_seconds ?? 0;
    return limit > 0 ? limit : -1;
  }
  if (game.total_time_seconds <= 0) return -1;
  let remaining = color === "black" ? game.black_time_left_seconds : game.white_time_left_seconds;
  if (activeGame.value && game.turn_started_at && turn.value === color) {
    remaining -= Math.floor((nowTick.value - new Date(game.turn_started_at).getTime()) / 1000);
  }
  return Math.max(0, remaining);
}

function formatSeconds(seconds: number) {
  if (seconds < 0) return "不限";
  const value = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function showGameFeedback(kind: "start" | "end", title: string, detail: string) {
  gameFeedback.value = { kind, title, detail };
  if (feedbackTimer !== null) window.clearTimeout(feedbackTimer);
  feedbackTimer = window.setTimeout(() => {
    gameFeedback.value = null;
    feedbackTimer = null;
  }, kind === "start" ? 2600 : 4200);
}

function winnerLabel(winner: string) {
  if (winner === "black") return "黑棋";
  if (winner === "white") return "白棋";
  return "双方";
}

function endReasonLabel(reason: string) {
  if (reason === "forbidden") return "黑棋禁手判负";
  if (reason === "time") return "超时判负";
  if (reason === "surrender") return "投降结束";
  if (reason === "leave" || reason === "disconnect_timeout") return "离线结束";
  if (reason === "draw" || reason === "timeout") return "平局";
  return "五子连珠";
}

function openPlayerDetail(id?: number | null) {
  if (id) selectedPlayerId.value = id;
}

function openRoomSettings() {
  if (!room.value) return;
  roomSettingsForm.value = {
    name: room.value.name,
    rule_set: room.value.rule_set,
    has_password: room.value.has_password,
    password: "",
    move_time_seconds: room.value.move_time_seconds,
    total_time_minutes: room.value.total_time_seconds > 0 ? Math.round(room.value.total_time_seconds / 60) : 0,
  };
  roomSettingsError.value = "";
  roomSettingsOpen.value = true;
}

async function submitRoomSettings() {
  roomSettingsError.value = "";
  try {
    const updated = await api.updateRoomSettings(roomId, {
      name: roomSettingsForm.value.name.trim(),
      rule_set: roomSettingsForm.value.rule_set,
      has_password: roomSettingsForm.value.has_password,
      password: roomSettingsForm.value.password,
      move_time_seconds: Number(roomSettingsForm.value.move_time_seconds),
      total_time_seconds: Number(roomSettingsForm.value.total_time_minutes) * 60,
    });
    room.value = updated;
    roomSettingsOpen.value = false;
    notice.value = "房间参数已更新。";
    await loadState(false);
  } catch (err) {
    roomSettingsError.value = errorMessage(err, "房间参数更新失败");
  }
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
  pendingOptimisticMoves.value = pendingOptimisticMoves.value.filter(
    (pending) => !state.moves.some((move) => move.x === pending.x && move.y === pending.y),
  );
  room.value = state.room;
  moves.value = [
    ...state.moves,
    ...pendingOptimisticMoves.value.filter((pending) => !state.moves.some((move) => move.x === pending.x && move.y === pending.y)),
  ];
  messages.value = state.messages;
  if (authState.user && ![state.room.black_player, state.room.white_player].includes(authState.user.id) && !state.room.spectators.some((seat) => seat.user === authState.user?.id)) {
    notice.value = "你已不在该房间。";
    window.setTimeout(() => router.push("/rooms"), 700);
    return;
  }
  if (state.moves.length > previousMoveCount) playStoneSound();
  if (previousRoom && state.messages.length > previousMessageCount) playChatSound();
  syncPendingRequests(state.room);
  const previousGame = previousRoom?.current_game;
  const nextGame = state.room.current_game;
  if (nextGame?.status === "playing" && (previousGame?.id !== nextGame.id || previousGame?.status !== "playing")) {
    playGameStartSound();
    showGameFeedback("start", "对局开始", "黑棋先手，双方计时已经启动。");
  } else if (nextGame?.status === "finished" && previousGame?.id === nextGame.id && previousGame.status === "playing") {
    playGameEndSound();
    showGameFeedback("end", nextGame.winner ? `${winnerLabel(nextGame.winner)}获胜` : "本局结束", endReasonLabel(nextGame.end_reason));
  }
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

function errorMessage(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback;
}

function isTransientError(err: unknown) {
  const message = errorMessage(err, "");
  return (
    message.includes("网络连接不稳定")
    || message.includes("无法连接服务器")
    || message.includes("服务器暂时不可用")
    || message.includes("请求失败（5")
    || message.includes("请求过于频繁")
  );
}

async function loadState(redirectOnError = false) {
  if (stateLoadInFlight) return false;
  stateLoadInFlight = true;
  try {
    applyState(await api.roomState(roomId));
    return true;
  } catch (err) {
    const message = errorMessage(err, "房间加载失败");
    if (redirectOnError || !isTransientError(err)) {
      notice.value = message;
    }
    if (redirectOnError && !isTransientError(err)) router.push("/rooms");
    return false;
  } finally {
    stateLoadInFlight = false;
  }
}

async function load() {
  if (!isAuthenticated()) {
    router.push("/rooms");
    return;
  }
  await loadState(true);
  statePollTimer = window.setInterval(() => {
    void loadState(false);
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
    heartbeatTimer = window.setInterval(() => sendSocket({ type: "ping" }), 5000);
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "state") applyState(data.state);
    if (data.type === "error") {
      ownUndoPending.value = false;
      ownSeatSwitchPending.value = false;
      pendingOptimisticMoves.value = [];
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
      if (data.online && data.user_id !== authState.user?.id) {
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
      reconnectTimer = window.setTimeout(connectSocket, 2000);
    }
  };
  socket.onerror = () => {
    socketConnected.value = false;
    socket?.close();
  };
}

function sendSocket(payload: object) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  try {
    socket.send(JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

async function play(x: number, y: number) {
  if (!canMove.value) return;
  const color = myColor.value;
  if (!color) return;
  const before = moves.value;
  const pendingMove = { x, y, color, player: authState.user?.id };
  pendingOptimisticMoves.value = [pendingMove];
  moves.value = [...moves.value.filter((move) => move.x !== x || move.y !== y), pendingMove];
  playStoneSound();
  notice.value = "落子已发送。";
  try {
    await api.move(roomId, x, y);
    void loadState(false);
  } catch (err) {
    if (isTransientError(err)) {
      notice.value = "网络波动，正在重新同步落子。";
      window.setTimeout(() => void loadState(false), 1200);
      window.setTimeout(() => {
        if (!pendingOptimisticMoves.value.some((move) => move.x === x && move.y === y)) return;
        pendingOptimisticMoves.value = [];
        moves.value = before;
        void loadState(false);
      }, 3500);
      return;
    }
    pendingOptimisticMoves.value = [];
    moves.value = before;
    notice.value = errorMessage(err, "落子失败");
  }
}

async function sendChat() {
  const text = draft.value.trim();
  if (!text) return;
  draft.value = "";
  try {
    await api.chat(roomId, text);
    void loadState(false);
  } catch (err) {
    if (isTransientError(err)) {
      notice.value = "网络波动，聊天消息未确认，请稍后再试。";
      return;
    }
    notice.value = errorMessage(err, "发送聊天失败");
  }
}

async function switchPosition(targetSeat: string) {
  if (!canInitiateSeatSwitch.value || targetSeat === currentSeatKey.value) return;
  try {
    await api.switchPosition(roomId, targetSeat);
    void loadState(false);
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，换位操作未确认。" : errorMessage(err, "换位失败");
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
  try {
    await api.readyRoom(roomId, nextReady);
    void loadState(false);
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，准备状态未确认。" : errorMessage(err, "准备状态更新失败");
  }
}

async function requestUndo() {
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
  api.requestUndo(roomId)
    .then(() => loadState(false))
    .catch((err) => {
      ownUndoPending.value = false;
      notice.value = isTransientError(err) ? "网络波动，悔棋申请未确认。" : errorMessage(err, "悔棋申请失败");
    });
}

async function respondUndo(accepted: boolean) {
  try {
    const result = await api.respondUndo(roomId, accepted);
    notice.value = result.detail;
    undoRequest.value = null;
    await loadState(false);
  } catch (err) {
    ownUndoPending.value = false;
    notice.value = isTransientError(err) ? "网络波动，悔棋回应未确认。" : errorMessage(err, "处理悔棋申请失败");
  }
}

function acceptUndo() {
  void respondUndo(true);
}

function rejectUndo() {
  void respondUndo(false);
}

async function respondSeatSwitch(accepted: boolean) {
  try {
    const result = await api.respondSeatSwitch(roomId, accepted);
    notice.value = result.detail;
    seatSwitchRequest.value = null;
    await loadState(false);
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，换位回应未确认。" : errorMessage(err, "处理换位申请失败");
  }
}

function acceptSeatSwitch() {
  void respondSeatSwitch(true);
}

function rejectSeatSwitch() {
  void respondSeatSwitch(false);
}

async function surrenderGame() {
  if (!activeGame.value || !myColor.value) return;
  try {
    await api.surrender(roomId);
    notice.value = "你已投降，本局结束。";
    await loadState(false);
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，投降操作未确认。" : errorMessage(err, "投降失败");
  }
}

async function kickUser(userId: number) {
  if (!isHost.value) return;
  try {
    await api.kickRoomUser(roomId, userId);
    notice.value = "已移出该玩家。";
    await loadState(false);
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，踢出操作未确认。" : errorMessage(err, "踢出失败");
  }
}

async function inviteUser(userId: number) {
  if (!isHost.value) return;
  try {
    await api.inviteRoomUser(roomId, userId);
    const user = inviteCandidates.value.find((candidate) => candidate.id === userId);
    sentInviteLabels.value[userId] = "已发送";
    notice.value = `已向 ${user?.username || "该玩家"} 发送邀请。`;
  } catch (err) {
    notice.value = isTransientError(err) ? "网络波动，邀请未确认。" : errorMessage(err, "邀请失败");
  }
}

async function leave() {
  try {
    await api.leaveRoom(roomId);
  } finally {
    socket?.close();
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
  if (feedbackTimer !== null) window.clearTimeout(feedbackTimer);
  socket?.close();
});
</script>

<template>
  <main class="page-shell">
    <header class="page-header"><div><button class="link-button" type="button" @click="leave">‹ 返回大厅</button><h1>{{ room?.name || "房间" }}</h1><p>黑棋在上，白棋在下；两名玩家都准备后开始。</p></div></header>
    <section class="game-layout">
      <div class="board-panel">
        <div v-if="gameFeedback" :class="['game-feedback', `game-feedback-${gameFeedback.kind}`]">
          <strong>{{ gameFeedback.title }}</strong>
          <span>{{ gameFeedback.detail }}</span>
        </div>
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
            <button class="secondary-button danger-button" :disabled="!activeGame || !myColor" type="button" @click="surrenderGame">投降</button>
          </div>
        </div>
        <div class="control-notice board-notice" :class="{ warning: notice.includes('失败') || notice.includes('断开') || notice.includes('不能') || notice.includes('用完') }">{{ notice }}</div>
        <GameBoard :stones="moves" :interactive="canMove" @play="play" />
      </div>
      <aside class="settings-panel">
        <div class="section-title-row">
          <div><h2>玩家</h2><p>{{ isHost ? "房主可以调整房间参数。" : "查看席位、准备状态和用时。" }}</p></div>
          <button v-if="isHost" class="icon-button" type="button" title="房间设置" @click="openRoomSettings"><Settings2 :size="18" /></button>
        </div>
        <div class="seat-list">
          <div class="seat-row">
            <div class="seat-player"><button v-if="room?.black_player" class="avatar-button" type="button" title="查看玩家信息" @click="openPlayerDetail(room.black_player)"><Avatar :username="room?.black_player_name || '等待'" :avatar-url="room?.black_player_avatar_url" /></button><Avatar v-else :username="room?.black_player_name || '等待'" :avatar-url="room?.black_player_avatar_url" /><div><strong>{{ room?.black_player_name || "等待好友加入" }} <span class="seat-inline-label seat-badge-black">黑棋</span><span v-if="room?.host === room?.black_player" class="seat-inline-label">房主</span></strong><span class="seat-meta-line"><span :class="['ready-badge', room?.black_ready ? 'ready' : 'waiting']">{{ room?.black_ready ? "已准备" : "未准备" }}</span><span class="time-pill">{{ formatSeconds(blackTimeLeft) }}</span></span></div></div>
            <div class="inline-actions"><button class="secondary-button" :disabled="!canSwitchTo('black')" @click="switchPosition('black')">{{ seatButtonLabel('black', Boolean(room?.black_player)) }}</button><button v-if="isHost && room?.black_player && room.black_player !== authState.user?.id" class="secondary-button danger-button" type="button" @click="kickUser(room.black_player)">踢出</button></div>
          </div>
          <div class="seat-row">
            <div class="seat-player"><button v-if="room?.white_player" class="avatar-button" type="button" title="查看玩家信息" @click="openPlayerDetail(room.white_player)"><Avatar :username="room?.white_player_name || '等待'" :avatar-url="room?.white_player_avatar_url" /></button><Avatar v-else :username="room?.white_player_name || '等待'" :avatar-url="room?.white_player_avatar_url" /><div><strong>{{ room?.white_player_name || "等待好友加入" }} <span class="seat-inline-label seat-badge-white">白棋</span><span v-if="room?.host === room?.white_player" class="seat-inline-label">房主</span></strong><span class="seat-meta-line"><span :class="['ready-badge', room?.white_ready ? 'ready' : 'waiting']">{{ room?.white_ready ? "已准备" : "未准备" }}</span><span class="time-pill">{{ formatSeconds(whiteTimeLeft) }}</span></span></div></div>
            <div class="inline-actions"><button class="secondary-button" :disabled="!canSwitchTo('white')" @click="switchPosition('white')">{{ seatButtonLabel('white', Boolean(room?.white_player)) }}</button><button v-if="isHost && room?.white_player && room.white_player !== authState.user?.id" class="secondary-button danger-button" type="button" @click="kickUser(room.white_player)">踢出</button></div>
          </div>
        </div>
        <div class="spectator-panel">
          <h2>观战席</h2>
          <div class="spectator-list">
            <div v-for="slot in spectatorSlots" :key="slot.seatNumber" class="spectator-row">
              <div class="spectator-main"><button v-if="slot.user" class="avatar-button" type="button" title="查看玩家信息" @click="openPlayerDetail(slot.user.user)"><Avatar :username="slot.user.username" :avatar-url="slot.user.avatar_url" /></button><Avatar v-else username="空位" avatar-url="" /><span class="seat-badge">观众{{ slot.seatNumber }}</span><strong>{{ slot.user?.username || "空位" }}</strong><span v-if="slot.user && room?.host === slot.user.user" class="seat-inline-label">房主</span></div>
              <div class="inline-actions"><button class="secondary-button" :disabled="!canSwitchTo(`spectator${slot.seatNumber}`)" @click="switchPosition(`spectator${slot.seatNumber}`)">{{ seatButtonLabel(`spectator${slot.seatNumber}`, Boolean(slot.user)) }}</button><button v-if="isHost && slot.user && slot.user.user !== authState.user?.id" class="secondary-button danger-button" type="button" @click="kickUser(slot.user.user)">踢出</button></div>
            </div>
          </div>
        </div>
        <div v-if="isHost" class="invite-panel">
          <h2>邀请在线玩家</h2>
          <div v-if="inviteCandidates.length === 0" class="empty-state">暂无可邀请的在线玩家。</div>
          <div v-else class="invite-list">
            <button v-for="user in inviteCandidates" :key="user.id" class="secondary-button" type="button" @click="inviteUser(user.id)">
              {{ user.username }} · {{ sentInviteLabels[user.id] || `${user.stats.wins} 胜` }}
            </button>
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
    <Modal v-if="roomSettingsOpen" title="房间设置" @close="roomSettingsOpen = false">
      <form class="modal-form" @submit.prevent="submitRoomSettings">
        <p v-if="roomSettingsError" class="form-error">{{ roomSettingsError }}</p>
        <label>房间名<input v-model="roomSettingsForm.name" /></label>
        <label>规则<select v-model="roomSettingsForm.rule_set"><option value="standard">无禁手</option><option value="renju">有禁手</option></select></label>
        <div class="form-subtitle">计时设置</div>
        <label>每步限时<select v-model.number="roomSettingsForm.move_time_seconds"><option :value="0">不限</option><option :value="15">15 秒</option><option :value="30">30 秒</option><option :value="60">60 秒</option><option :value="120">120 秒</option></select></label>
        <label>每方局时<select v-model.number="roomSettingsForm.total_time_minutes"><option :value="0">不限</option><option :value="5">5 分钟</option><option :value="10">10 分钟</option><option :value="15">15 分钟</option><option :value="30">30 分钟</option></select></label>
        <label class="checkbox-row"><input v-model="roomSettingsForm.has_password" type="checkbox" />设置房间口令</label>
        <label v-if="roomSettingsForm.has_password">新房间口令<input v-model="roomSettingsForm.password" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="text" name="room-settings-code" type="text" placeholder="留空则保留原口令" /></label>
        <button class="primary-button" type="submit">保存设置</button>
      </form>
    </Modal>
    <PlayerDetailModal v-if="selectedPlayerId" :user-id="selectedPlayerId" @close="selectedPlayerId = null" />
  </main>
</template>
