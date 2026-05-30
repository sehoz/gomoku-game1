from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .ai import choose_ai_move
from .models import ChatMessage, GameSession, Room
from .presence import online_users_payload
from .rules import evaluate_move
from .serializers import (
    ChatMessageSerializer,
    LoginSerializer,
    MatchRecordSerializer,
    RegisterSerializer,
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
    join_room,
    leave_room,
    make_move,
    room_stones,
    set_ready,
    switch_position,
)


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
        GameSession.objects.filter(status=GameSession.STATUS_FINISHED)
        .filter(Q(black_player=request.user) | Q(white_player=request.user))
        .select_related("room", "black_player", "white_player")
        .prefetch_related("moves")
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
@permission_classes([AllowAny])
def online_users(request):
    return Response({"users": online_users_payload()})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def rooms(request):
    cleanup_idle_rooms()
    if request.method == "GET":
        queryset = (
            Room.objects.filter(Q(black_player__isnull=False) | Q(white_player__isnull=False) | Q(spectators__isnull=False))
            .exclude(status=Room.STATUS_FINISHED)
            .select_related("black_player", "white_player", "current_game")
            .prefetch_related("spectators__user")
        )
        return Response(RoomSerializer(queryset.distinct(), many=True).data)

    name = (request.data.get("name") or "未命名房间").strip() or "未命名房间"
    if Room.objects.exclude(status=Room.STATUS_FINISHED).filter(name__iexact=name).exists():
        return Response({"detail": "房间名重复"}, status=status.HTTP_400_BAD_REQUEST)
    rule_set = request.data.get("rule_set", Room.RULE_STANDARD)
    if rule_set not in {Room.RULE_STANDARD, Room.RULE_RENJU}:
        return Response({"detail": "规则参数无效"}, status=status.HTTP_400_BAD_REQUEST)
    room = Room(name=name[:80], rule_set=rule_set, black_player=request.user)
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
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_room_view(request, room_id):
    try:
        room = leave_room(Room.objects.get(id=room_id), request.user)
        return Response({"room": RoomSerializer(room).data if room else None})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)


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
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except SeatSwitchNeedsConsent as exc:
        return Response({"detail": str(exc), "request": exc.request}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ready_view(request, room_id):
    try:
        room = set_ready(Room.objects.get(id=room_id), request.user, request.data.get("ready", True))
        return Response(RoomSerializer(room).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def move_view(request, room_id):
    try:
        room, result = make_move(Room.objects.get(id=room_id), request.user, request.data.get("x"), request.data.get("y"))
        return Response({"room": RoomSerializer(room).data, "result": result.__dict__})
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request, room_id):
    try:
        message = add_chat(Room.objects.get(id=room_id), request.user, request.data.get("text", ""))
        return Response(ChatMessageSerializer(message).data)
    except Room.DoesNotExist:
        return Response({"detail": "房间不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
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
