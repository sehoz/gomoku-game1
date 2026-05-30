from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/", views.register),
    path("auth/login/", views.login),
    path("auth/logout/", views.logout),
    path("auth/me/", views.me),
    path("online/", views.online_users),
    path("rooms/", views.rooms),
    path("rooms/<int:room_id>/join/", views.join_room_view),
    path("rooms/<int:room_id>/leave/", views.leave_room_view),
    path("rooms/<int:room_id>/state/", views.room_state),
    path("rooms/<int:room_id>/switch-seat/", views.switch_seat_view),
    path("rooms/<int:room_id>/move/", views.move_view),
    path("rooms/<int:room_id>/chat/", views.chat_view),
    path("solo/ai-move/", views.solo_ai_move),
]
