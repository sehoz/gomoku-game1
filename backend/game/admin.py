from django.contrib import admin

from .models import ChatMessage, GameSession, HiddenMatchRecord, Move, PlayerProfile, Room, RoomInvitation, SpectatorSeat


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "rule_set", "status", "players_count", "spectators_count", "move_time_seconds", "total_time_seconds", "created_at")
    search_fields = ("name",)


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("room", "game", "move_number", "color", "x", "y", "created_at")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("room_name", "status", "winner", "black_time_left_seconds", "white_time_left_seconds", "started_at", "ended_at")
    search_fields = ("room_name", "black_player__username", "white_player__username")


@admin.register(HiddenMatchRecord)
class HiddenMatchRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "hidden_at")
    search_fields = ("user__username", "game__room_name")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender_name", "text", "created_at")


@admin.register(SpectatorSeat)
class SpectatorSeatAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "seat_number", "joined_at")


@admin.register(RoomInvitation)
class RoomInvitationAdmin(admin.ModelAdmin):
    list_display = ("room", "inviter", "invitee", "status", "created_at", "responded_at")


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "last_seen_at")
    search_fields = ("user__username",)
