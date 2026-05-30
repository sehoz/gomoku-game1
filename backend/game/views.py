from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .ai import choose_ai_move
from .models import ChatMessage, GameSession, Room, RoomInvitation
from .presence import online_users_payload
from .rules import evaluate_move
from .serializers import (
    ChatMessageSerializer,
    GameReplaySerializer,
    LeaderboardEntrySerializer,
    LoginSerializer,
    MatchRecordSerializer,
    RegisterSerializer,
    RoomInvitationSerializer,
    RoomSerializer,
    RoomStateSerializer,
    UserSerializer,
)
from .services import (
    SeatSwitchNeedsConsent,
    active_or_latest_game,
    add_chat,
    cleanup_idle_rooms,
    ensure_room_member,
    ensure_room_host,
    finish_if_turn_timed_out,
    create_room_invitation,
    join_room,
    kick_user,
    leave_room,
    mark_room_seen,
    make_move,
    accept_pending_seat_switch,
    accept_pending_undo,
    reject_pending_seat_switch,
    reject_pending_undo,
    request_undo,
    respond_room_invitation,
    room_stones,
    set_ready,
    store_pending_seat_switch,
    surrender,
    switch_position,
)


def broadcast_room_state(room_id):
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(f"room_{room_id}", {"type": "room.state"})


def token_response(user):
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data})


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    username = serializer.validated_data["username"].strip()
    password = serializer.validated_data["password"]
    if not username:
        return Response({"detail": "请输入用户名"}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "该用户名已经被注册"}, status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(username=username, password=password)
    return token_response(user)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    username = serializer.validated_data["username"].strip()
    if not username:
        return Response({"detail": "请输入用户名"}, status=status.HTTP_400_BAD_REQUEST)
    user = authenticate(username=username, password=serializer.validated_data["password"])
    if not user:
        return Response({"detail": "用户名或密码错误"}, status=status.HTTP_400_BAD_REQUEST)
    return token_response(user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"user": None})
    return Response({"user": UserSerializer(request.user).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_history(request):
    queryset = (
        GameSession.objects.filter(status=GameSession.STATUS_FINISHED, moves__isnull=False)
        .filter(Q(black_player=request.user) | Q(white_player=request.user))
        .select_related("room", "black_player", "white_player")
        .prefetch_related("moves")
        .distinct()
        .order_by("-ended_at", "-started_at")[:20]
    )
    records = []
    for game in queryset:
        color = "black" if game.black_player_id == request.user.id else "white"
        opponent = game.white_player if color == "black" else game.black_player
        if game.winner == color:
            result = "win"
        elif game.winner in {"black", "white"}:
            result = "loss"
        elif game.end_reason == "draw":
            result = "draw"
        else:
            result = "unfinished"
        records.append(
            {
                "id": game.id,
                "room_name": game.room.name if game.room else game.room_name,
                "rule_set": game.rule_set,
                "color": color,
                "result": result,
                "opponent": {
                    "id": opponent.id if opponent else None,
                    "username": opponent.username if opponent else "未知玩家",
                },
                "started_at": game.started_at,
                "ended_at": game.ended_at,
                "end_reason": game.end_reason,
                "moves_count": game.moves.count(),
            }
        )
    return Response({"records": MatchRecordSerializer(records, many=True).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_detail(request, match_id):
    try:
        game = (
            GameSession.objects.select_related("black_player", "white_player", "room")
            .prefetch_related("moves")
            .get(id=match_id, status=GameSession.STATUS_FINISHED)
        )
    except GameSession.DoesNotExist:
        return Response({"detail": "对局不存在"}, status=status.HTTP_404_NOT_FOUND)
    if request.user.id not in {game.black_player_id, game.white_player_id}:
        return Response({"detail": "无权查看该棋谱"}, status=status.HTTP_403_FORBIDDEN)
    data = {
        "id": game.id,
        "room_name": game.room.name if game.room else game.room_name,
        "rule_set": game.rule_set,
        "black_player": {
            "id": game.black_player_id,
            "username": game.black_player.username if game.black_player else "未知玩家",
        },
        "white_player": {
            "id": game.white_player_id,
            "username": game.white_player.username if game.white_player else "未知玩家",
        },
        "winner": game.winner,
        "end_reason": game.end_reason,
        "started_at": game.started_at,
        "ended_at": game.ended_at,
        "moves": game.moves.all(),
    }
    return Response(GameReplaySerializer(data).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def leaderboard(request):
    entries = []
    users = User.objects.all().order_by("username")
    for user in users:
        stats = UserSerializer(user).data["stats"]
        entries.append(
            {
                "user": {"id": user.id, "username": user.username},
                "wins": stats["wins"],
                "totalGames": stats["totalGames"],
                "winRate": stats["winRate"],
            }
        )
    entries = sorted(entries, key=lambda item: (-item["wins"], item["user"]["username"]))[:5]
    for index, entry in enumerate(entries, start=1):
        entry["rank"] = index
    return Response({"entries": LeaderboardEntrySerializer(entries, many=True).data})


@api_view(["GET"])
@permission_classes([AllowAny])
def online_users(request):
    return Response({"users": online_users_payload()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_invitations(request):
    invitations = (
        RoomInvitation.objects.filter(invitee=request.user, status=RoomInvitation.STATUS_PENDING)
        .select_related("room", "inviter")
        .order_by("-created_at")[:10]
    )
    return Response({"invitations": RoomInvitationSerializer(invitations, many=True).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_invitation_view(request, invitation_id):
    try:
        room, invitation = respond_room_invitation(
            RoomInvitation.objects.get(id=invitation_id),
            request.user,
            bool(request.data.get("accepted")),
        )
    except RoomInvitation.DoesNotExist:
        return Response({"detail": "邀请不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if room:
        broadcast_room_state(room.id)
    return Response(
        {
            "invitation": RoomInvitationSerializer(invitation).data,
            "room": RoomSerializer(room).data if room else None,
        }
    )


def active_rooms_queryset():
    return (
        Room.objects.filter(Q(black_player__isnull=False) | Q(white_player__isnull=False) | Q(spectators__isnull=False))
        .exclude(status=Room.STATUS_FINISHED)
        .distinct()
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def room_count(request):
    cleanup_idle_rooms()
    return Response({"count": active_rooms_queryset().count()})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def rooms(request):
    cleanup_idle_rooms()
    if request.method == "GET":
        queryset = (
            active_rooms_queryset()
            .select_related("black_player", "white_player", "current_game")
            .prefetch_related("spectators__user")
        )
        for room in queryset:
            ensure_room_host(room)
        return Response(RoomSerializer(queryset, many=True).data)

    name = (request.data.get("name") or "未命名房间").strip() or "未命名房间"
    if Room.objects.exclude(status=Room.STATUS_FINISHED).filter(name__iexact=name).exists():
        return Response({"detail": "房间名重复"}, status=status.HTTP_400_BAD_REQUEST)
    rule_set = request.data.get("rule_set", Room.RULE_STANDARD)
    if rule_set not in {Room.RULE_STANDARD, Room.RULE_RENJU}:
        return Response({"detail": "规则参数无效"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        move_time_seconds = int(request.data.get("move_time_seconds", 30))
        total_time_seconds = int(request.data.get("total_time_seconds", 600))
    except (TypeError, ValueError):
        return Response({"detail": "计时参数无效"}, status=status.HTTP_400_BAD_REQUEST)
    if not 10 <= move_time_seconds <= 300:
        return Response({"detail": "步时需要设置在 10 到 300 秒之间"}, status=status.HTTP_400_BAD_REQUEST)
    if not 60 <= total_time_seconds <= 7200:
        return Response({"detail": "局时需要设置在 1 到 120 分钟之间"}, status=status.HTTP_400_BAD_REQUEST)
    room = Room(
        name=name[:80],
        rule_set=rule_set,
        black_player=request.user,
        host=request.user,
        black_joined_at=timezone.now(),
        move_time_seconds=move_time_seconds,
        total_time_seconds=total_time_seconds,
    )
    password = request.data.get("password", "")
    room.set_password(password if request.data.get("has_password") else "")
    room.refresh_status()
    room.save()
    add_chat(room, request.user, "房间已创建。")
    return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_room_view(request, room_id):
    try:
        room = join_room(Room.objects.get(id=room_id), request.user, request.data.get("password", ""))
        broadcast_room_state(room.id)
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_room_view(request, room_id):
    try:
        room = leave_room(Room.objects.get(id=room_id), request.user)
        if room:
            broadcast_room_state(room.id)
        return Response({"room": RoomSerializer(room).data if room else None})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kick_room_user_view(request, room_id):
    try:
        room = kick_user(Room.objects.get(id=room_id), request.user, request.data.get("user_id"))
        if room:
            broadcast_room_state(room.id)
        return Response({"room": RoomSerializer(room).data if room else None})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except (TypeError, ValueError) as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_room_user_view(request, room_id):
    try:
        invitee = User.objects.get(id=request.data.get("user_id"))
        invitation = create_room_invitation(Room.objects.get(id=room_id), request.user, invitee)
        return Response({"invitation": RoomInvitationSerializer(invitation).data})
    except User.DoesNotExist:
        return Response({"detail": "邀请的玩家不存在"}, status=status.HTTP_404_NOT_FOUND)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def room_state(request, room_id):
    cleanup_idle_rooms()
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    try:
        ensure_room_member(room, request.user)
    except ValueError:
        return Response({"detail": "请先加入房间"}, status=status.HTTP_403_FORBIDDEN)
    ensure_room_host(room)
    mark_room_seen(room, request.user, throttle_seconds=10)
    room.refresh_from_db()
    room, timed_out = finish_if_turn_timed_out(room)
    if timed_out:
        broadcast_room_state(room.id)
    game = active_or_latest_game(room)
    data = {
        "room": room,
        "moves": game.moves.all() if game else room.moves.filter(game__isnull=True),
        "messages": room.messages.all()[:100],
    }
    return Response(RoomStateSerializer(data).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def switch_seat_view(request, room_id):
    try:
        room = switch_position(
            Room.objects.get(id=room_id),
            request.user,
            request.data.get("target_seat") or request.data.get("target_color"),
        )
        broadcast_room_state(room.id)
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except SeatSwitchNeedsConsent as exc:
        store_pending_seat_switch(room_id, exc.request)
        broadcast_room_state(room_id)
        return Response({"detail": str(exc), "request": exc.request}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ready_view(request, room_id):
    try:
        room = set_ready(Room.objects.get(id=room_id), request.user, request.data.get("ready", True))
        broadcast_room_state(room.id)
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def move_view(request, room_id):
    try:
        room, result = make_move(Room.objects.get(id=room_id), request.user, request.data.get("x"), request.data.get("y"))
        broadcast_room_state(room.id)
        return Response({"room": RoomSerializer(room).data, "result": result.__dict__})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def surrender_view(request, room_id):
    try:
        room = surrender(Room.objects.get(id=room_id), request.user)
        broadcast_room_state(room.id)
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request, room_id):
    try:
        message = add_chat(Room.objects.get(id=room_id), request.user, request.data.get("text", ""))
        broadcast_room_state(room_id)
        return Response(ChatMessageSerializer(message).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def undo_request_view(request, room_id):
    try:
        undo = request_undo(Room.objects.get(id=room_id), request.user)
        broadcast_room_state(room_id)
        return Response({"request": undo})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def undo_response_view(request, room_id):
    try:
        if request.data.get("accepted"):
            result = accept_pending_undo(Room.objects.get(id=room_id), request.user)
            broadcast_room_state(room_id)
            return Response({"accepted": True, "detail": f"{result['requester']} 悔棋成功，已撤销 {result['removed']} 手。"})
        reject_pending_undo(Room.objects.get(id=room_id), request.user)
        broadcast_room_state(room_id)
        return Response({"accepted": False, "detail": f"{request.user.username} 拒绝了悔棋申请。"})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def seat_switch_response_view(request, room_id):
    try:
        if request.data.get("accepted"):
            result = accept_pending_seat_switch(Room.objects.get(id=room_id), request.user)
            broadcast_room_state(room_id)
            return Response({"accepted": True, "detail": f"{result['requester']} 已换到{result['target_label']}。"})
        reject_pending_seat_switch(Room.objects.get(id=room_id), request.user)
        broadcast_room_state(room_id)
        return Response({"accepted": False, "detail": f"{request.user.username} 拒绝了换位申请。"})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        broadcast_room_state(room_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def solo_ai_move(request):
    stones = request.data.get("stones", [])
    board_size = int(request.data.get("board_size", 15))
    ai_color = request.data.get("ai_color", "white")
    rule_set = request.data.get("rule_set", Room.RULE_STANDARD)
    ai_level = request.data.get("ai_level", "normal")
    move = choose_ai_move(stones, board_size, ai_color, rule_set, ai_level)
    if not move:
        return Response({"move": None, "result": {"status": "draw"}})
    result = evaluate_move(stones, move["x"], move["y"], ai_color, rule_set, board_size)
    return Response({"move": move, "result": result.__dict__})
