import json
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.db.models import Q
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework.authtoken.models import Token

from .presence import mark_offline, mark_online, online_users_payload
from .models import Room
from .serializers import RoomStateSerializer
from .services import (
    SeatSwitchNeedsConsent,
    accept_seat_switch,
    active_game,
    active_or_latest_game,
    add_chat,
    finish_if_player_timed_out,
    leave_room,
    mark_room_seen,
    make_move,
    set_ready,
    switch_position,
    touch_room,
    undo_last_turn,
    undo_remaining,
    user_color,
)

ROOM_CONNECTIONS = {}


def connection_counts(room_id):
    return ROOM_CONNECTIONS.setdefault(int(room_id), {})


def register_connection(room_id, user_id):
    counts = connection_counts(room_id)
    counts[user_id] = counts.get(user_id, 0) + 1


def unregister_connection(room_id, user_id):
    counts = connection_counts(room_id)
    if user_id not in counts:
        return
    counts[user_id] -= 1
    if counts[user_id] <= 0:
        counts.pop(user_id, None)
    if not counts:
        ROOM_CONNECTIONS.pop(int(room_id), None)


def is_connected(room_id, user_id):
    return connection_counts(room_id).get(user_id, 0) > 0


@sync_to_async
def user_from_token(token_key):
    try:
        return Token.objects.select_related("user").get(key=token_key).user
    except Token.DoesNotExist:
        return None


@sync_to_async
def is_room_member(room_id, user):
    return (
        Room.objects.filter(id=room_id)
        .filter(Q(black_player=user) | Q(white_player=user) | Q(spectators__user=user))
        .distinct()
        .exists()
    )


@sync_to_async
def mark_room_active(room_id, user=None):
    try:
        room = Room.objects.get(id=room_id)
        if user:
            mark_room_seen(room, user)
            room.refresh_from_db()
            finished_room, finished = finish_if_player_timed_out(room)
            return {"finished": finished, "room_id": finished_room.id}
        touch_room(room)
    except Room.DoesNotExist:
        pass
    return {"finished": False, "room_id": int(room_id)}


@sync_to_async
def serialize_state(room_id):
    room = Room.objects.get(id=room_id)
    game = active_or_latest_game(room)
    return RoomStateSerializer(
        {
            "room": room,
            "moves": game.moves.all() if game else room.moves.filter(game__isnull=True),
            "messages": room.messages.all()[:100],
        }
    ).data


@sync_to_async
def create_chat(room_id, user, text):
    return add_chat(Room.objects.get(id=room_id), user, text).id


@sync_to_async
def create_move(room_id, user, x, y):
    room = Room.objects.get(id=room_id)
    color = user_color(room, user)
    if color == "black" and room.white_player_id and not is_connected(room_id, room.white_player_id):
        raise ValueError("白棋已离线，等待对方重连或超时结束")
    if color == "white" and room.black_player_id and not is_connected(room_id, room.black_player_id):
        raise ValueError("黑棋已离线，等待对方重连或超时结束")
    room, result = make_move(room, user, x, y)
    return result.__dict__


@sync_to_async
def change_position(room_id, user, target_seat):
    try:
        switch_position(Room.objects.get(id=room_id), user, target_seat)
        return {"status": "switched"}
    except SeatSwitchNeedsConsent as exc:
        return {"status": "needs_consent", "request": exc.request}


@sync_to_async
def accept_position_request(room_id, request, responder):
    accept_seat_switch(Room.objects.get(id=room_id), request, responder)
    return {
        "requester": request["requester_username"],
        "from_label": request["from_label"],
        "target_label": request["target_label"],
    }


@sync_to_async
def change_ready(room_id, user, ready):
    return set_ready(Room.objects.get(id=room_id), user, ready).id


@sync_to_async
def leave_current_room(room_id, user):
    try:
        room = leave_room(Room.objects.get(id=room_id), user)
    except Room.DoesNotExist:
        return False
    return room is not None


@sync_to_async
def create_undo_request(room_id, user):
    room = Room.objects.get(id=room_id)
    color = user_color(room, user)
    if color is None:
        raise ValueError("你不在该房间")
    if room.players_count < 2:
        raise ValueError("等待另一名玩家加入")
    game = active_game(room)
    if not game:
        raise ValueError("当前没有进行中的对局")
    if not game.moves.filter(player=user).exists():
        raise ValueError("当前没有可以悔棋的落子")
    if undo_remaining(game, color) <= 0:
        raise ValueError("本局悔棋次数已用完")
    mark_room_seen(room, user)
    return {"user_id": user.id, "username": user.username, "color": color}


@sync_to_async
def accept_undo_request(room_id, requester_id, responder):
    room = Room.objects.get(id=room_id)
    if user_color(room, responder) is None:
        raise ValueError("你不在该房间")
    if requester_id == responder.id:
        raise ValueError("不能接受自己的悔棋申请")
    requester = None
    if room.black_player_id == requester_id:
        requester = room.black_player
    elif room.white_player_id == requester_id:
        requester = room.white_player
    if requester is None:
        raise ValueError("申请悔棋的玩家已离开房间")
    _room, removed = undo_last_turn(room, requester)
    return {"removed": removed, "requester": requester.username}


@sync_to_async
def reject_undo_request(room_id):
    try:
        touch_room(Room.objects.get(id=room_id))
    except Room.DoesNotExist:
        pass


@sync_to_async
def online_payload():
    return online_users_payload()


@sync_to_async
def set_presence_online(user_id, channel_name):
    mark_online(user_id, channel_name)


@sync_to_async
def set_presence_offline(user_id, channel_name):
    mark_offline(user_id, channel_name)


class RoomConsumer(AsyncWebsocketConsumer):
    pending_undo_requests = {}
    pending_seat_switch_requests = {}

    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        query = parse_qs(self.scope["query_string"].decode())
        token = (query.get("token") or [""])[0]
        self.user = await user_from_token(token)
        if not self.user or not await is_room_member(self.room_id, self.user):
            await self.close(code=4401)
            return

        self.group_name = f"room_{self.room_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        register_connection(self.room_id, self.user.id)
        await mark_room_active(self.room_id, self.user)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "peer.status", "user_id": self.user.id, "username": self.user.username, "online": True},
        )
        await self.send_state()

    async def disconnect(self, _close_code):
        if hasattr(self, "group_name"):
            unregister_connection(self.room_id, self.user.id)
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "peer.status", "user_id": self.user.id, "username": self.user.username, "online": False},
            )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
            event_type = payload.get("type")
            if event_type == "chat":
                await create_chat(self.room_id, self.user, payload.get("text", ""))
                await self.broadcast_state()
            elif event_type == "ping":
                result = await mark_room_active(self.room_id, self.user)
                if result.get("finished"):
                    await self.broadcast_state()
            elif event_type == "move":
                await create_move(self.room_id, self.user, payload.get("x"), payload.get("y"))
                await self.broadcast_state()
            elif event_type in {"switch_seat", "switch_position"}:
                target_seat = payload.get("target_seat") or payload.get("target_color")
                result = await change_position(self.room_id, self.user, target_seat)
                if result["status"] == "needs_consent":
                    self.pending_seat_switch_requests[int(self.room_id)] = result["request"]
                    await self.channel_layer.group_send(
                        self.group_name,
                        {"type": "seat.switch.request", "request": result["request"]},
                    )
                else:
                    await self.broadcast_state()
            elif event_type == "seat_switch_accept":
                request = self.pending_seat_switch_requests.get(int(self.room_id))
                if not request:
                    await self.send_json({"type": "error", "detail": "当前没有待处理的换位申请"})
                    return
                result = await accept_position_request(self.room_id, request, self.user)
                self.pending_seat_switch_requests.pop(int(self.room_id), None)
                await self.broadcast_state()
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "seat.switch.result",
                        "accepted": True,
                        "detail": f"{result['requester']} 已换到{result['target_label']}。",
                    },
                )
            elif event_type == "seat_switch_reject":
                request = self.pending_seat_switch_requests.get(int(self.room_id))
                if request:
                    if request["target_user_id"] != self.user.id:
                        await self.send_json({"type": "error", "detail": "只有目标位置上的玩家可以拒绝换位"})
                        return
                    self.pending_seat_switch_requests.pop(int(self.room_id), None)
                    await reject_undo_request(self.room_id)
                    await self.channel_layer.group_send(
                        self.group_name,
                        {"type": "seat.switch.result", "accepted": False, "detail": f"{self.user.username} 拒绝了换位申请。"},
                    )
            elif event_type == "ready":
                await change_ready(self.room_id, self.user, payload.get("ready", True))
                await self.broadcast_state()
            elif event_type == "leave":
                room_exists = await leave_current_room(self.room_id, self.user)
                if room_exists:
                    await self.broadcast_state()
                else:
                    await self.broadcast_closed()
                await self.close()
            elif event_type == "undo_request":
                request = await create_undo_request(self.room_id, self.user)
                self.pending_undo_requests[int(self.room_id)] = request
                await self.channel_layer.group_send(self.group_name, {"type": "undo.request", "request": request})
            elif event_type == "undo_accept":
                request = self.pending_undo_requests.get(int(self.room_id))
                if not request:
                    await self.send_json({"type": "error", "detail": "当前没有待处理的悔棋申请"})
                    return
                result = await accept_undo_request(self.room_id, request["user_id"], self.user)
                self.pending_undo_requests.pop(int(self.room_id), None)
                await self.broadcast_state()
                await self.channel_layer.group_send(self.group_name, {"type": "undo.result", "accepted": True, "detail": f"{result['requester']} 悔棋成功，已撤销 {result['removed']} 手。"})
            elif event_type == "undo_reject":
                request = self.pending_undo_requests.pop(int(self.room_id), None)
                if request:
                    await reject_undo_request(self.room_id)
                    await self.channel_layer.group_send(self.group_name, {"type": "undo.result", "accepted": False, "detail": f"{self.user.username} 拒绝了悔棋申请。"})
        except Exception as exc:
            await self.send_json({"type": "error", "detail": str(exc)})

    async def broadcast_state(self):
        await self.channel_layer.group_send(self.group_name, {"type": "room.state"})

    async def broadcast_closed(self):
        await self.channel_layer.group_send(self.group_name, {"type": "room.closed"})

    async def room_state(self, _event):
        await self.send_state()

    async def room_closed(self, _event):
        await self.send_json({"type": "closed"})

    async def undo_request(self, event):
        await self.send_json({"type": "undo_request", "request": event["request"]})

    async def undo_result(self, event):
        await self.send_json({"type": "undo_result", "accepted": event["accepted"], "detail": event["detail"]})

    async def seat_switch_request(self, event):
        await self.send_json({"type": "seat_switch_request", "request": event["request"]})

    async def seat_switch_result(self, event):
        await self.send_json({"type": "seat_switch_result", "accepted": event["accepted"], "detail": event["detail"]})

    async def peer_status(self, event):
        await self.send_json(
            {
                "type": "peer_status",
                "user_id": event["user_id"],
                "username": event["username"],
                "online": event["online"],
            }
        )

    async def send_state(self):
        state = await serialize_state(self.room_id)
        await self.send_json({"type": "state", "state": state})

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))


class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        token = (query.get("token") or [""])[0]
        self.user = await user_from_token(token) if token else None
        self.group_name = "presence"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        if self.user:
            await set_presence_online(self.user.id, self.channel_name)
            await self.broadcast_presence()
        await self.send_presence()

    async def disconnect(self, _close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if getattr(self, "user", None):
            await set_presence_offline(self.user.id, self.channel_name)
            await self.broadcast_presence()

    async def receive(self, text_data=None, bytes_data=None):
        await self.send_presence()

    async def broadcast_presence(self):
        await self.channel_layer.group_send(self.group_name, {"type": "presence.state"})

    async def presence_state(self, _event):
        await self.send_presence()

    async def send_presence(self):
        users = await online_payload()
        await self.send(text_data=json.dumps({"type": "presence", "users": users}, ensure_ascii=False))
