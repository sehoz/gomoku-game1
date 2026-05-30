from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ChatMessage, GameSession, Move, Room, SpectatorSeat
from .rules import RuleResult, evaluate_move, next_turn

UNDO_LIMIT = 3


class SeatSwitchNeedsConsent(ValueError):
    def __init__(self, request):
        super().__init__("目标位置已有玩家，需要对方同意")
        self.request = request


def spectator_number_from_key(value):
    return value[len("spectator") :]


def room_stones(room):
    game = active_or_latest_game(room)
    queryset = game.moves if game else room.moves.filter(game__isnull=True)
    return [
        {"x": move.x, "y": move.y, "color": move.color}
        for move in queryset.order_by("move_number")
    ]


def user_color(room, user):
    if room.black_player_id == user.id:
        return "black"
    if room.white_player_id == user.id:
        return "white"
    return None


def spectator_seat(room, user):
    if not room.pk:
        return None
    return room.spectators.filter(user=user).first()


def normalize_seat_key(seat):
    value = (seat or "").strip().lower()
    if value in {"black", "white"}:
        return value
    if value.startswith("spectator"):
        number = spectator_number_from_key(value)
        if number.isdigit() and int(number) >= 1:
            return f"spectator{int(number)}"
    raise ValueError("目标位置无效")


def seat_label(seat):
    key_value = normalize_seat_key(seat)
    if key_value == "black":
        return "黑棋"
    if key_value == "white":
        return "白棋"
    return f"观众{spectator_number_from_key(key_value)}"


def user_seat(room, user):
    if room.black_player_id == user.id:
        return "black"
    if room.white_player_id == user.id:
        return "white"
    seat = spectator_seat(room, user)
    if seat:
        return f"spectator{seat.seat_number}"
    return None


def seat_user(room, seat):
    key_value = normalize_seat_key(seat)
    if key_value == "black":
        return room.black_player
    if key_value == "white":
        return room.white_player
    seat_number = int(spectator_number_from_key(key_value))
    spectator = room.spectators.select_related("user").filter(seat_number=seat_number).first()
    return spectator.user if spectator else None


def participant_role(room, user):
    return user_seat(room, user)


def ensure_room_member(room, user):
    if participant_role(room, user) is None:
        raise ValueError("你不在该房间")


def opponent_color(color):
    return "white" if color == "black" else "black"


def role_suffix(room, user):
    role = participant_role(room, user)
    if role == "black":
        return "黑棋"
    if role == "white":
        return "白棋"
    if role and role.startswith("spectator"):
        return f"观众{spectator_number_from_key(role)}"
    return "访客"


def display_sender_name(room, user):
    return f"{user.username}（{role_suffix(room, user)}）"


def touch_room(room):
    if not room.pk:
        return room
    room.last_activity_at = timezone.now()
    room.save(update_fields=["last_activity_at"])
    return room


def player_last_seen_field(color):
    return "black_last_seen_at" if color == "black" else "white_last_seen_at"


def mark_room_seen(room, user, throttle_seconds=None):
    if not room.pk:
        return room
    now = timezone.now()
    previous_activity = room.last_activity_at
    update_fields = ["last_activity_at"]
    room.last_activity_at = now
    color = user_color(room, user)
    if throttle_seconds is not None and color:
        field = player_last_seen_field(color)
        previous_seen = getattr(room, field)
        if (
            previous_seen
            and previous_seen > now - timedelta(seconds=throttle_seconds)
            and previous_activity
            and previous_activity > now - timedelta(seconds=throttle_seconds)
        ):
            return room
    if color:
        field = player_last_seen_field(color)
        setattr(room, field, now)
        update_fields.append(field)
    room.save(update_fields=update_fields)
    return room


def active_game(room):
    game = room.current_game
    if game and game.status == GameSession.STATUS_PLAYING:
        return game
    return None


def active_or_latest_game(room):
    return room.current_game or room.games.order_by("-started_at").first()


def start_game(room):
    if room.current_game and room.current_game.status == GameSession.STATUS_PLAYING:
        return room.current_game
    now = timezone.now()
    room.black_ready = True
    room.white_ready = True
    game = GameSession.objects.create(
        room=room,
        room_name=room.name,
        black_player=room.black_player,
        white_player=room.white_player,
        rule_set=room.rule_set,
        started_at=now,
        move_time_seconds=room.move_time_seconds,
        total_time_seconds=room.total_time_seconds,
        black_time_left_seconds=room.total_time_seconds,
        white_time_left_seconds=room.total_time_seconds,
        turn_started_at=now,
    )
    room.current_game = game
    room.winner = ""
    room.status = Room.STATUS_PLAYING
    room.black_last_seen_at = room.black_last_seen_at or now
    room.white_last_seen_at = room.white_last_seen_at or now
    room.last_activity_at = now
    room.save(
        update_fields=[
            "current_game",
            "winner",
            "status",
            "black_ready",
            "white_ready",
            "black_last_seen_at",
            "white_last_seen_at",
            "last_activity_at",
        ]
    )
    return game


def finish_game(room, winner="", reason="finished"):
    game = active_game(room)
    if not game:
        return room
    now = timezone.now()
    if not game.moves.exists():
        room.current_game = None
        room.winner = ""
        room.status = Room.STATUS_WAITING
        room.black_ready = False
        room.white_ready = False
        room.last_activity_at = now
        room.save(update_fields=["current_game", "winner", "status", "black_ready", "white_ready", "last_activity_at"])
        game.delete()
        return room
    game.winner = winner or ""
    game.status = GameSession.STATUS_FINISHED
    game.end_reason = reason
    game.ended_at = now
    game.save(update_fields=["winner", "status", "end_reason", "ended_at"])
    room.winner = winner or ""
    room.status = Room.STATUS_WAITING
    room.black_ready = False
    room.white_ready = False
    room.last_activity_at = now
    room.save(update_fields=["winner", "status", "black_ready", "white_ready", "last_activity_at"])
    return room


def undo_used(game, color):
    return game.black_undo_used if color == "black" else game.white_undo_used


def undo_remaining(game, color):
    return max(UNDO_LIMIT - undo_used(game, color), 0)


def increment_undo_used(game, color):
    if color == "black":
        game.black_undo_used += 1
        return "black_undo_used"
    game.white_undo_used += 1
    return "white_undo_used"


def timeout_minutes():
    return getattr(settings, "ROOM_IDLE_MINUTES", 5)


def current_turn_color(game):
    return "black" if game.moves.count() % 2 == 0 else "white"


def time_left_field(color):
    return "black_time_left_seconds" if color == "black" else "white_time_left_seconds"


def turn_elapsed_seconds(game, now=None):
    if not game.turn_started_at:
        return 0
    current = now or timezone.now()
    return max(0, (current - game.turn_started_at).total_seconds())


def displayed_time_left(game, color, now=None):
    remaining = getattr(game, time_left_field(color))
    if game.status == GameSession.STATUS_PLAYING and current_turn_color(game) == color:
        remaining -= int(turn_elapsed_seconds(game, now))
    return max(0, remaining)


def finish_if_turn_timed_out(room):
    game = active_game(room)
    if not game:
        return room, False
    now = timezone.now()
    color = current_turn_color(game)
    elapsed = turn_elapsed_seconds(game, now)
    remaining = getattr(game, time_left_field(color))
    if elapsed >= game.move_time_seconds or elapsed >= remaining:
        return finish_game(room, opponent_color(color), "time"), True
    return room, False


def finish_if_player_timed_out(room):
    if not active_game(room):
        return room, False
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes())
    black_old = room.black_last_seen_at and room.black_last_seen_at < cutoff
    white_old = room.white_last_seen_at and room.white_last_seen_at < cutoff
    if black_old and white_old:
        return finish_game(room, "", "timeout"), True
    if black_old:
        return finish_game(room, "white", "disconnect_timeout"), True
    if white_old:
        return finish_game(room, "black", "disconnect_timeout"), True
    return room, False


def cleanup_idle_rooms():
    cutoff = timezone.now() - timedelta(minutes=getattr(settings, "ROOM_IDLE_MINUTES", 5))
    deleted = Room.objects.filter(
        status=Room.STATUS_WAITING,
        games__isnull=True,
        last_activity_at__lt=cutoff,
    ).delete()[0]
    for room in Room.objects.filter(status=Room.STATUS_PLAYING, last_activity_at__lt=cutoff):
        finish_game(room, "", "timeout")
    return deleted


def first_free_spectator_number(room):
    occupied = set(room.spectators.values_list("seat_number", flat=True))
    for number in range(1, room.max_spectators + 1):
        if number not in occupied:
            return number
    return None


def game_started(room):
    return bool(active_game(room))


def assert_user_can_initiate_switch(room, user):
    if user_color(room, user) and game_started(room):
        raise ValueError("对局已经开始，黑棋和白棋不能换位置")


def clear_user_seat(room, user):
    was_player = False
    if room.black_player_id == user.id:
        room.black_player = None
        room.black_ready = False
        was_player = True
    if room.white_player_id == user.id:
        room.white_player = None
        room.white_ready = False
        was_player = True
    room.spectators.filter(user=user).delete()
    if was_player:
        room.black_ready = False
        room.white_ready = False


def assign_user_to_seat(room, user, seat):
    key_value = normalize_seat_key(seat)
    if key_value.startswith("spectator"):
        seat_number = int(spectator_number_from_key(key_value))
        if seat_number > room.max_spectators:
            raise ValueError("目标观战席不存在")
        SpectatorSeat.objects.update_or_create(room=room, user=user, defaults={"seat_number": seat_number})
    elif key_value == "black":
        room.black_player = user
    elif key_value == "white":
        room.white_player = user


def build_seat_switch_request(room, user, target_seat, target_user):
    from_seat = user_seat(room, user)
    if not from_seat:
        raise ValueError("你不在该房间")
    return {
        "requester_id": user.id,
        "requester_username": user.username,
        "target_user_id": target_user.id,
        "target_username": target_user.username,
        "from_seat": from_seat,
        "from_label": seat_label(from_seat),
        "target_seat": normalize_seat_key(target_seat),
        "target_label": seat_label(target_seat),
    }


def apply_direct_seat_move(room, user, target_seat):
    clear_user_seat(room, user)
    assign_user_to_seat(room, user, target_seat)
    room.refresh_status()
    room.last_activity_at = timezone.now()
    room.save()
    return room


@transaction.atomic
def join_room(room, user, password=""):
    room = Room.objects.select_for_update().get(id=room.id)
    if room.has_password and not room.password_matches(password):
        raise ValueError("房间密码不正确")
    if room.black_player_id == user.id or room.white_player_id == user.id:
        mark_room_seen(room, user)
        return room
    existing_spectator = spectator_seat(room, user)
    if existing_spectator and room.players_count >= room.max_players:
        mark_room_seen(room, user)
        return room
    if room.status == Room.STATUS_FINISHED:
        raise ValueError("房间已结束")
    if room.black_player_id is None:
        room.black_player = user
        if existing_spectator:
            existing_spectator.delete()
    elif room.white_player_id is None:
        room.white_player = user
        if existing_spectator:
            existing_spectator.delete()
    else:
        number = first_free_spectator_number(room)
        if number is None:
            raise ValueError("房间已满")
        SpectatorSeat.objects.create(room=room, user=user, seat_number=number)
    room.refresh_status()
    room.last_activity_at = timezone.now()
    room.save()
    mark_room_seen(room, user)
    return room


@transaction.atomic
def leave_room(room, user):
    room = Room.objects.select_for_update().get(id=room.id)
    if game_started(room):
        color = user_color(room, user)
        if room.status == Room.STATUS_PLAYING and color:
            finish_game(room, opponent_color(color), "leave")
        else:
            touch_room(room)
        room.refresh_from_db()
    if room.black_player_id == user.id:
        room.black_player = None
        room.black_ready = False
        room.white_ready = False
    if room.white_player_id == user.id:
        room.white_player = None
        room.black_ready = False
        room.white_ready = False
    room.spectators.filter(user=user).delete()
    if room.occupants_count == 0:
        room.delete()
        return None
    room.refresh_status()
    room.last_activity_at = timezone.now()
    room.save()
    return room


@transaction.atomic
def switch_seat(room, user, target_color):
    return switch_position(room, user, target_color)


@transaction.atomic
def switch_position(room, user, target_seat):
    room = Room.objects.select_for_update().get(id=room.id)
    target_seat = normalize_seat_key(target_seat)
    current_seat = user_seat(room, user)
    if current_seat is None:
        raise ValueError("你不在该房间")
    if current_seat == target_seat:
        mark_room_seen(room, user)
        return room
    assert_user_can_initiate_switch(room, user)
    target_user = seat_user(room, target_seat)
    if target_user and target_user.id != user.id:
        if user_color(room, target_user) and game_started(room):
            raise ValueError("对局已经开始，黑棋和白棋不能换位置")
        raise SeatSwitchNeedsConsent(build_seat_switch_request(room, user, target_seat, target_user))
    return apply_direct_seat_move(room, user, target_seat)


@transaction.atomic
def accept_seat_switch(room, request, responder):
    room = Room.objects.select_for_update().get(id=room.id)
    requester_id = int(request["requester_id"])
    target_user_id = int(request["target_user_id"])
    if responder.id != target_user_id:
        raise ValueError("只有目标位置上的玩家可以同意换位")
    requester_seat = request["from_seat"]
    target_seat = request["target_seat"]
    target_user = seat_user(room, target_seat)
    if not target_user or target_user.id != responder.id:
        raise ValueError("目标位置已经发生变化")
    requester = room.black_player if room.black_player_id == requester_id else room.white_player if room.white_player_id == requester_id else None
    if requester is None:
        seat = room.spectators.select_related("user").filter(user_id=requester_id).first()
        requester = seat.user if seat else None
    if requester is None:
        raise ValueError("申请换位的用户已经离开房间")
    if user_seat(room, requester) != requester_seat:
        raise ValueError("申请换位的用户位置已经发生变化")
    assert_user_can_initiate_switch(room, requester)
    assert_user_can_initiate_switch(room, responder)

    clear_user_seat(room, requester)
    clear_user_seat(room, responder)
    assign_user_to_seat(room, requester, target_seat)
    assign_user_to_seat(room, responder, requester_seat)
    room.refresh_status()
    room.last_activity_at = timezone.now()
    room.save()
    return room


@transaction.atomic
def set_ready(room, user, ready=True):
    room = Room.objects.select_for_update().get(id=room.id)
    color = user_color(room, user)
    if color is None:
        raise ValueError("只有黑棋或白棋玩家可以准备")
    if active_game(room):
        raise ValueError("对局已经开始，不能修改准备状态")
    if color == "black":
        room.black_ready = bool(ready)
    else:
        room.white_ready = bool(ready)
    now = timezone.now()
    setattr(room, player_last_seen_field(color), now)
    if room.players_count == 2 and room.black_ready and room.white_ready:
        room.black_last_seen_at = room.black_last_seen_at or now
        room.white_last_seen_at = room.white_last_seen_at or now
        start_game(room)
        return room
    room.refresh_status()
    room.last_activity_at = now
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
    room, timed_out = finish_if_player_timed_out(room)
    if timed_out:
        return room, RuleResult(True, "对局已因玩家离线超时结束", status=f"{room.winner}_win" if room.winner else "draw", winner=room.winner)
    room, timed_out = finish_if_turn_timed_out(room)
    if timed_out:
        return room, RuleResult(True, "对局已因走棋超时结束", status=f"{room.winner}_win" if room.winner else "draw", winner=room.winner)
    game = active_game(room)
    if not game:
        raise ValueError("双方准备后才能开始对局")
    mark_room_seen(room, user)

    stones = room_stones(room)
    if next_turn(stones) != color:
        raise ValueError("当前不是你的回合")

    result = evaluate_move(stones, int(x), int(y), color, room.rule_set, 15)
    if not result.ok:
        raise ValueError(result.reason)

    now = timezone.now()
    elapsed = turn_elapsed_seconds(game, now)
    if elapsed >= game.move_time_seconds:
        finish_game(room, opponent_color(color), "time")
        return room, RuleResult(True, "本步落子超时，对局已结束", status=f"{opponent_color(color)}_win", winner=opponent_color(color))
    if elapsed >= getattr(game, time_left_field(color)):
        finish_game(room, opponent_color(color), "time")
        return room, RuleResult(True, "总用时耗尽，对局已结束", status=f"{opponent_color(color)}_win", winner=opponent_color(color))

    Move.objects.create(
        room=room,
        game=game,
        player=user,
        move_number=len(stones) + 1,
        x=int(x),
        y=int(y),
        color=color,
    )
    remaining_field = time_left_field(color)
    setattr(game, remaining_field, max(0, int(getattr(game, remaining_field) - elapsed)))
    game.turn_started_at = now
    game.save(update_fields=[remaining_field, "turn_started_at"])
    if result.winner:
        finish_game(room, result.winner, "forbidden" if result.forbidden else "win")
    elif result.status == "draw":
        finish_game(room, "", "draw")
    else:
        touch_room(room)
    return room, result


@transaction.atomic
def undo_last_turn(room, requester):
    room = Room.objects.select_for_update().get(id=room.id)
    requester_color = user_color(room, requester)
    if requester_color is None:
        raise ValueError("你不在该房间")
    game = active_game(room)
    if not game:
        raise ValueError("当前没有进行中的对局")
    if undo_remaining(game, requester_color) <= 0:
        raise ValueError("本局悔棋次数已用完")
    moves = list(game.moves.select_for_update().order_by("-move_number")[:2])
    if not moves:
        raise ValueError("当前没有可以悔棋的落子")

    delete_ids = []
    latest = moves[0]
    if latest.player_id == requester.id:
        delete_ids.append(latest.id)
    elif len(moves) >= 2 and moves[1].player_id == requester.id:
        delete_ids.extend([latest.id, moves[1].id])
    else:
        raise ValueError("只能撤销你的上一步落子")

    Move.objects.filter(id__in=delete_ids).delete()
    room.winner = ""
    undo_field = increment_undo_used(game, requester_color)
    game.turn_started_at = timezone.now()
    game.save(update_fields=[undo_field, "turn_started_at"])
    room.refresh_status()
    room.last_activity_at = timezone.now()
    room.save(update_fields=["status", "winner", "last_activity_at"])
    return room, len(delete_ids)


def add_chat(room, user, text):
    ensure_room_member(room, user)
    text = text.strip()
    if not text:
        raise ValueError("聊天内容不能为空")
    message = ChatMessage.objects.create(room=room, sender=user, sender_name=display_sender_name(room, user), text=text[:500])
    touch_room(room)
    return message
