from django.contrib import admin

from .models import ChatMessage, GameSession, Move, Room, SpectatorSeat


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_set", "status", "players_count", "spectators_count", "created_at")
    search_fields = ("name",)


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("room", "game", "move_number", "color", "x", "y", "created_at")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("room_name", "status", "winner", "started_at", "ended_at")
    search_fields = ("room_name", "black_player__username", "white_player__username")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender_name", "text", "created_at")


@admin.register(SpectatorSeat)
class SpectatorSeatAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "seat_number", "joined_at")
