from django.contrib.auth.models import User
from rest_framework import serializers

from .models import ChatMessage, Move, Room


class UserSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "stats")

    def get_stats(self, user):
        finished = Room.objects.filter(status=Room.STATUS_FINISHED).filter(
            black_player=user
        ) | Room.objects.filter(status=Room.STATUS_FINISHED).filter(white_player=user)
        total = finished.count()
        wins = finished.filter(winner__in=["black", "white"]).filter(
            black_player=user,
            winner="black",
        ).count() + finished.filter(white_player=user, winner="white").count()
        losses = max(total - wins, 0)
        return {
            "totalGames": total,
            "wins": wins,
            "losses": losses,
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
            "players",
            "max_players",
            "black_player",
            "black_player_name",
            "white_player",
            "white_player_name",
            "winner",
        )
        read_only_fields = ("id", "created_at", "status", "winner")

    def get_players(self, room):
        return room.players_count


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
