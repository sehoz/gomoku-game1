import json
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.db.models import Q
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework.authtoken.models import Token

from .models import Room
from .serializers import RoomStateSerializer
from .services import add_chat, leave_room, make_move, switch_seat


@sync_to_async
def user_from_token(token_key):
    try:
        return Token.objects.select_related("user").get(key=token_key).user
    except Token.DoesNotExist:
        return None


@sync_to_async
def is_room_member(room_id, user):
    return Room.objects.filter(id=room_id).filter(Q(black_player=user) | Q(white_player=user)).exists()


@sync_to_async
def serialize_state(room_id):
    room = Room.objects.get(id=room_id)
    return RoomStateSerializer(
        {
            "room": room,
            "moves": room.moves.all(),
            "messages": room.messages.all()[:100],
        }
    ).data


@sync_to_async
def create_chat(room_id, user, text):
    return add_chat(Room.objects.get(id=room_id), user, text).id


@sync_to_async
def create_move(room_id, user, x, y):
    room, result = make_move(Room.objects.get(id=room_id), user, x, y)
    return result.__dict__


@sync_to_async
def change_seat(room_id, user, target_color):
    return switch_seat(Room.objects.get(id=room_id), user, target_color).id


@sync_to_async
def leave_current_room(room_id, user):
    try:
        room = leave_room(Room.objects.get(id=room_id), user)
    except Room.DoesNotExist:
        return False
    return room is not None


class RoomConsumer(AsyncWebsocketConsumer):
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
        await self.send_state()

    async def disconnect(self, _close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
            event_type = payload.get("type")
            if event_type == "chat":
                await create_chat(self.room_id, self.user, payload.get("text", ""))
                await self.broadcast_state()
            elif event_type == "move":
                await create_move(self.room_id, self.user, payload.get("x"), payload.get("y"))
                await self.broadcast_state()
            elif event_type == "switch_seat":
                await change_seat(self.room_id, self.user, payload.get("target_color"))
                await self.broadcast_state()
            elif event_type == "leave":
                room_exists = await leave_current_room(self.room_id, self.user)
                if room_exists:
                    await self.broadcast_state()
                else:
                    await self.broadcast_closed()
                await self.close()
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

    async def send_state(self):
        state = await serialize_state(self.room_id)
        await self.send_json({"type": "state", "state": state})

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))
