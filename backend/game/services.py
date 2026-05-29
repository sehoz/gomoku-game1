from django.db import transaction

from .models import ChatMessage, Move, Room
from .rules import evaluate_move, next_turn


def room_stones(room):
    return [
        {"x": move.x, "y": move.y, "color": move.color}
        for move in room.moves.order_by("move_number")
    ]


def user_color(room, user):
    if room.black_player_id == user.id:
        return "black"
    if room.white_player_id == user.id:
        return "white"
    return None


def ensure_room_member(room, user):
    if user_color(room, user) is None:
        raise ValueError("你不在该房间")


@transaction.atomic
def join_room(room, user, password=""):
    room = Room.objects.select_for_update().get(id=room.id)
    if room.has_password and not room.password_matches(password):
        raise ValueError("房间密码不正确")
    if room.black_player_id == user.id or room.white_player_id == user.id:
        return room
    if room.status == Room.STATUS_FINISHED:
        raise ValueError("房间已结束")
    if room.players_count >= room.max_players:
        raise ValueError("房间已满")
    if room.black_player_id is None:
        room.black_player = user
    elif room.white_player_id is None:
        room.white_player = user
    room.refresh_status()
    room.save()
    return room


@transaction.atomic
def leave_room(room, user):
    room = Room.objects.select_for_update().get(id=room.id)
    if room.black_player_id == user.id:
        room.black_player = None
    if room.white_player_id == user.id:
        room.white_player = None
    if room.players_count == 0:
        room.delete()
        return None
    room.refresh_status()
    room.save()
    return room


@transaction.atomic
def switch_seat(room, user, target_color):
    room = Room.objects.select_for_update().get(id=room.id)
    if room.players_count >= 2:
        raise ValueError("两人房间需要对方同意换位")
    if user_color(room, user) is None:
        raise ValueError("你不在该房间")
    if target_color == "black":
        room.black_player = user
        room.white_player = None
    elif target_color == "white":
        room.white_player = user
        room.black_player = None
    else:
        raise ValueError("目标棋色无效")
    room.refresh_status()
    room.save()
    return room


@transaction.atomic
def make_move(room, user, x, y):
    room = Room.objects.select_for_update().get(id=room.id)
    color = user_color(room, user)
    if color is None:
        raise ValueError("你不在该房间")
    if room.players_count < 2:
        raise ValueError("等待另一名玩家加入")
    if room.status == Room.STATUS_FINISHED:
        raise ValueError("对局已经结束")

    stones = room_stones(room)
    if next_turn(stones) != color:
        raise ValueError("当前不是你的回合")

    result = evaluate_move(stones, int(x), int(y), color, room.rule_set, 15)
    if not result.ok:
        raise ValueError(result.reason)

    Move.objects.create(
        room=room,
        player=user,
        move_number=len(stones) + 1,
        x=int(x),
        y=int(y),
        color=color,
    )
    if result.winner:
        room.winner = result.winner
        room.status = Room.STATUS_FINISHED
        room.save(update_fields=["winner", "status"])
    elif result.status == "draw":
        room.status = Room.STATUS_FINISHED
        room.save(update_fields=["status"])
    return room, result


def add_chat(room, user, text):
    ensure_room_member(room, user)
    text = text.strip()
    if not text:
        raise ValueError("聊天内容不能为空")
    return ChatMessage.objects.create(room=room, sender=user, sender_name=user.username, text=text[:500])
