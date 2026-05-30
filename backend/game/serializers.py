from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import serializers

from .models import ChatMessage, GameSession, Move, Room
from .services import displayed_time_left


class UserSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "stats")

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
    black_player_name = serializers.CharField(source="black_player.username", read_only=True)
    white_player_name = serializers.CharField(source="white_player.username", read_only=True)

    class Meta:
        model = Room
        fields = (
            "id",
            "name",
            "created_at",
            "has_password",
            "rule_set",
            "status",
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
            "black_ready",
            "black_undo_remaining",
            "white_player",
            "white_player_name",
            "white_ready",
            "white_undo_remaining",
            "winner",
        )
        read_only_fields = ("id", "created_at", "status", "winner")

    def get_players(self, room):
        return room.players_count

    def get_spectators_count(self, room):
        return room.spectators_count

    def get_spectators(self, room):
        spectators = room.spectators.select_related("user").order_by("seat_number")
        return [
            {
                "user": spectator.user_id,
                "username": spectator.user.username,
                "seat_number": spectator.seat_number,
                "stats": UserSerializer(spectator.user).data["stats"],
            }
            for spectator in spectators
        ]

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


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ("id", "sender", "sender_name", "text", "created_at")


class RoomStateSerializer(serializers.Serializer):
    room = RoomSerializer()
    moves = MoveSerializer(many=True)
    messages = ChatMessageSerializer(many=True)
