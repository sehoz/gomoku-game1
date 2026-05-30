from django.urls import path

from .consumers import PresenceConsumer, RoomConsumer

websocket_urlpatterns = [
    path("ws/presence/", PresenceConsumer.as_asgi()),
    path("ws/rooms/<int:room_id>/", RoomConsumer.as_asgi()),
]
