from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import serializers

from .models import ChatMessage, GameSession, Move, PlayerProfile, Room, RoomInvitation
from .services import decode_pending_request, displayed_time_left


class UserSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "avatar_url", "is_admin", "stats")

    def get_avatar_url(self, user):
        profile, _ = PlayerProfile.objects.get_or_create(user=user)
        return profile.avatar_data_url

    def get_is_admin(self, user):
        return bool(user.is_staff or user.is_superuser)

    def get_stats(self, user):
        finished = GameSession.objects.filter(status=GameSession.STATUS_FINISHED, moves__isnull=False).filter(
            black_player=user
        ) | GameSession.objects.filter(status=GameSession.STATUS_FINISHED, moves__isnull=False).filter(white_player=user)
        finished = finished.distinct()
        total = finished.count()
        wins = finished.filter(winner__in=["black", "white"]).filter(
            black_player=user,
            winner="black",
        ).count() + finished.filter(white_player=user, winner="white").count()
        losses = finished.filter(winner__in=["black", "white"]).exclude(
            Q(black_player=user, winner="black") | Q(white_player=user, winner="white")
        ).count()
        draws = max(total - wins - losses, 0)
        return {
            "totalGames": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "winRate": round(wins / total * 100) if total else 0,
        }


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=80)
    password = serializers.CharField(min_length=6, write_only=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)


class RoomSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()
    spectators_count = serializers.SerializerMethodField()
    spectators = serializers.SerializerMethodField()
    current_game = serializers.SerializerMethodField()
    black_undo_remaining = serializers.SerializerMethodField()
    white_undo_remaining = serializers.SerializerMethodField()
    pending_undo_request = serializers.SerializerMethodField()
    pending_seat_switch_request = serializers.SerializerMethodField()
    black_player_name = serializers.CharField(source="black_player.username", read_only=True)
    black_player_avatar_url = serializers.SerializerMethodField()
    white_player_name = serializers.CharField(source="white_player.username", read_only=True)
    white_player_avatar_url = serializers.SerializerMethodField()
    host_name = serializers.CharField(source="host.username", read_only=True)

    class Meta:
        model = Room
        fields = (
            "id",
            "name",
            "created_at",
            "has_password",
            "rule_set",
            "status",
            "host",
            "host_name",
            "current_game",
            "players",
            "max_players",
            "spectators_count",
            "max_spectators",
            "move_time_seconds",
            "total_time_seconds",
            "spectators",
            "black_player",
            "black_player_name",
            "black_player_avatar_url",
            "black_ready",
            "black_undo_remaining",
            "white_player",
            "white_player_name",
            "white_player_avatar_url",
            "white_ready",
            "white_undo_remaining",
            "winner",
            "pending_undo_request",
            "pending_seat_switch_request",
        )
        read_only_fields = ("id", "created_at", "status", "winner")

    def get_players(self, room):
        return room.players_count

    def get_spectators_count(self, room):
        return room.spectators_count

    def get_spectators(self, room):
        spectators = room.spectators.select_related("user").order_by("seat_number")
        seats = []
        for spectator in spectators:
            user_data = UserSerializer(spectator.user).data
            seats.append(
                {
                    "user": spectator.user_id,
                    "username": spectator.user.username,
                    "avatar_url": user_data["avatar_url"],
                    "seat_number": spectator.seat_number,
                    "stats": user_data["stats"],
                }
            )
        return seats

    def get_black_player_avatar_url(self, room):
        if not room.black_player_id:
            return ""
        return UserSerializer(room.black_player).data["avatar_url"]

    def get_white_player_avatar_url(self, room):
        if not room.white_player_id:
            return ""
        return UserSerializer(room.white_player).data["avatar_url"]

    def get_current_game(self, room):
        game = room.current_game
        if not game:
            return None
        return {
            "id": game.id,
            "status": game.status,
            "winner": game.winner,
            "end_reason": game.end_reason,
            "started_at": game.started_at,
            "ended_at": game.ended_at,
            "move_time_seconds": game.move_time_seconds,
            "total_time_seconds": game.total_time_seconds,
            "black_time_left_seconds": displayed_time_left(game, "black"),
            "white_time_left_seconds": displayed_time_left(game, "white"),
            "turn_started_at": game.turn_started_at,
        }

    def get_black_undo_remaining(self, room):
        game = room.current_game
        return max(3 - game.black_undo_used, 0) if game and game.status == GameSession.STATUS_PLAYING else 3

    def get_white_undo_remaining(self, room):
        game = room.current_game
        return max(3 - game.white_undo_used, 0) if game and game.status == GameSession.STATUS_PLAYING else 3

    def get_pending_undo_request(self, room):
        return decode_pending_request(room.pending_undo_request)

    def get_pending_seat_switch_request(self, room):
        return decode_pending_request(room.pending_seat_switch_request)


class MatchRecordSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    room_name = serializers.CharField()
    rule_set = serializers.CharField()
    color = serializers.CharField()
    result = serializers.CharField()
    opponent = serializers.DictField()
    started_at = serializers.DateTimeField(allow_null=True)
    ended_at = serializers.DateTimeField(allow_null=True)
    end_reason = serializers.CharField()
    moves_count = serializers.IntegerField()


class MoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Move
        fields = ("id", "move_number", "x", "y", "color", "player", "created_at")


class GameReplaySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    room_name = serializers.CharField()
    rule_set = serializers.CharField()
    black_player = serializers.DictField()
    white_player = serializers.DictField()
    winner = serializers.CharField()
    end_reason = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    ended_at = serializers.DateTimeField(allow_null=True)
    moves = MoveSerializer(many=True)


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    user = serializers.DictField()
    wins = serializers.IntegerField()
    totalGames = serializers.IntegerField()
    winRate = serializers.IntegerField()


class RoomInvitationSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source="room.name", read_only=True)
    inviter_username = serializers.CharField(source="inviter.username", read_only=True)

    class Meta:
        model = RoomInvitation
        fields = ("id", "room", "room_name", "inviter", "inviter_username", "status", "created_at")


class AdminUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "is_active", "is_staff", "is_superuser", "avatar_url", "date_joined")

    def get_avatar_url(self, user):
        profile, _ = PlayerProfile.objects.get_or_create(user=user)
        return profile.avatar_data_url


class AdminRoomSerializer(serializers.ModelSerializer):
    players_count = serializers.IntegerField(read_only=True)
    spectators_count = serializers.IntegerField(read_only=True)
    black_player_name = serializers.CharField(source="black_player.username", read_only=True)
    white_player_name = serializers.CharField(source="white_player.username", read_only=True)
    host_name = serializers.CharField(source="host.username", read_only=True)

    class Meta:
        model = Room
        fields = (
            "id",
            "name",
            "created_at",
            "rule_set",
            "status",
            "has_password",
            "black_player",
            "black_player_name",
            "white_player",
            "white_player_name",
            "host",
            "host_name",
            "players_count",
            "spectators_count",
            "move_time_seconds",
            "total_time_seconds",
            "last_activity_at",
        )


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ("id", "sender", "sender_name", "text", "created_at")


class RoomStateSerializer(serializers.Serializer):
    room = RoomSerializer()
    moves = MoveSerializer(many=True)
    messages = ChatMessageSerializer(many=True)
