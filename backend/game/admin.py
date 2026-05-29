from django.contrib import admin

from .models import ChatMessage, Move, Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_set", "status", "players_count", "created_at")
    search_fields = ("name",)


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("room", "move_number", "color", "x", "y", "created_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender_name", "text", "created_at")
