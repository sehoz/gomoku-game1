from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .ai import choose_ai_move
from .models import Room, SpectatorSeat
from .rules import evaluate_move
from .services import (
    SeatSwitchNeedsConsent,
    accept_seat_switch,
    add_chat,
    cleanup_idle_rooms,
    join_room,
    leave_room,
    make_move,
    set_ready,
    switch_position,
    undo_last_turn,
)


class AuthEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_duplicate_username_returns_clear_message(self):
        payload = {"username": "alice", "password": "gomoku123"}
        first = self.client.post("/api/auth/register/", payload, format="json")
        second = self.client.post("/api/auth/register/", payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["detail"], "该用户名已经被注册")

    def test_login_bad_password_returns_clear_message(self):
        User.objects.create_user(username="alice", password="gomoku123")

        response = self.client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "用户名或密码错误")

    def test_netlify_origin_is_allowed_by_cors(self):
        response = self.client.options(
            "/api/auth/register/",
            HTTP_ORIGIN="https://gomoku-example.netlify.app",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(response["access-control-allow-origin"], "https://gomoku-example.netlify.app")


class RuleEngineTests(TestCase):
    def test_standard_rule_allows_black_overline_as_win(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(5)]
        result = evaluate_move(stones, 5, 7, "black", Room.RULE_STANDARD)

        self.assertTrue(result.ok)
        self.assertEqual(result.winner, "black")

    def test_renju_black_overline_loses(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(5)]
        result = evaluate_move(stones, 5, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertTrue(result.forbidden)
        self.assertEqual(result.winner, "white")


class AiTests(TestCase):
    def test_ai_takes_immediate_win(self):
        stones = [{"x": x, "y": 7, "color": "white"} for x in range(4)]

        move = choose_ai_move(stones, 15, "white", Room.RULE_STANDARD, "hard")

        self.assertEqual(move, {"x": 4, "y": 7})

    def test_ai_blocks_opponent_immediate_win(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(4)]

        move = choose_ai_move(stones, 15, "white", Room.RULE_STANDARD, "hard")

        self.assertEqual(move, {"x": 4, "y": 7})

    def test_renju_allows_exact_five_for_black(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(4)]
        result = evaluate_move(stones, 4, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertEqual(result.winner, "black")

    def test_renju_black_double_four_loses(self):
        stones = [
            {"x": 5, "y": 7, "color": "black"},
            {"x": 6, "y": 7, "color": "black"},
            {"x": 8, "y": 7, "color": "black"},
            {"x": 7, "y": 5, "color": "black"},
            {"x": 7, "y": 6, "color": "black"},
            {"x": 7, "y": 8, "color": "black"},
        ]
        result = evaluate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertTrue(result.forbidden)
        self.assertEqual(result.winner, "white")

    def test_renju_black_double_three_loses(self):
        stones = [
            {"x": 6, "y": 7, "color": "black"},
            {"x": 8, "y": 7, "color": "black"},
            {"x": 7, "y": 6, "color": "black"},
            {"x": 7, "y": 8, "color": "black"},
        ]
        result = evaluate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertTrue(result.forbidden)
        self.assertEqual(result.winner, "white")


class RoomLifecycleTests(TestCase):
    def playable_room(self, black, white):
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)
        room.black_ready = True
        room.white_ready = True
        room.refresh_status()
        room.save()
        return room

    def test_last_player_leave_deletes_room(self):
        user = User.objects.create_user(username="alice", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=user)
        room.refresh_status()
        room.save()

        result = leave_room(room, user)

        self.assertIsNone(result)
        self.assertFalse(Room.objects.filter(id=room.id).exists())

    def test_undo_latest_own_move_removes_one_stone(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        make_move(room, black, 7, 7)

        _room, removed = undo_last_turn(room, black)

        self.assertEqual(removed, 1)
        self.assertEqual(room.moves.count(), 0)

    def test_undo_after_opponent_response_removes_two_stones(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        make_move(room, black, 7, 7)
        make_move(room, white, 7, 8)

        _room, removed = undo_last_turn(room, black)

        self.assertEqual(removed, 2)
        self.assertEqual(room.moves.count(), 0)

    def test_room_name_must_be_unique_among_active_rooms(self):
        owner = User.objects.create_user(username="owner", password="gomoku123")
        Room.objects.create(name="好友对局", black_player=owner)
        client = APIClient()
        client.force_authenticate(owner)

        response = client.post("/api/rooms/", {"name": "好友对局", "rule_set": "standard"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "房间名重复")

    def test_third_joiner_becomes_spectator_and_chat_has_role_suffix(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        watcher = User.objects.create_user(username="watcher", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)

        joined = join_room(room, watcher)
        message = add_chat(joined, watcher, "大家好")

        self.assertEqual(joined.players_count, 2)
        self.assertEqual(joined.spectators_count, 1)
        self.assertTrue(SpectatorSeat.objects.filter(room=joined, user=watcher, seat_number=1).exists())
        self.assertEqual(message.sender_name, "watcher（观众1）")

    def test_both_players_must_ready_before_move(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)

        with self.assertRaisesMessage(ValueError, "双方准备后才能开始对局"):
            make_move(room, black, 7, 7)

        set_ready(room, black, True)
        room.refresh_from_db()
        self.assertEqual(room.status, Room.STATUS_WAITING)
        set_ready(room, white, True)
        room.refresh_from_db()
        self.assertEqual(room.status, Room.STATUS_PLAYING)
        make_move(room, black, 7, 7)
        self.assertEqual(room.moves.count(), 1)

    def test_switch_to_empty_spectator_seat_directly(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black)

        switched = switch_position(room, black, "spectator1")

        self.assertIsNone(switched.black_player)
        self.assertTrue(SpectatorSeat.objects.filter(room=switched, user=black, seat_number=1).exists())

    def test_occupied_seat_requires_consent_and_accept_swaps_positions(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)

        with self.assertRaises(SeatSwitchNeedsConsent) as context:
            switch_position(room, black, "white")

        accept_seat_switch(room, context.exception.request, white)
        room.refresh_from_db()
        self.assertEqual(room.black_player, white)
        self.assertEqual(room.white_player, black)

    def test_player_cannot_switch_after_start_but_spectator_can(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        watcher = User.objects.create_user(username="watcher", password="gomoku123")
        room = self.playable_room(black, white)
        SpectatorSeat.objects.create(room=room, user=watcher, seat_number=1)

        with self.assertRaisesMessage(ValueError, "对局已经开始，黑棋和白棋不能换位置"):
            switch_position(room, black, "spectator2")

        switched = switch_position(room, watcher, "spectator2")
        self.assertTrue(SpectatorSeat.objects.filter(room=switched, user=watcher, seat_number=2).exists())

    @override_settings(ROOM_IDLE_MINUTES=5)
    def test_cleanup_idle_waiting_rooms(self):
        user = User.objects.create_user(username="owner", password="gomoku123")
        room = Room.objects.create(name="旧房间", black_player=user)
        Room.objects.filter(id=room.id).update(last_activity_at=timezone.now() - timedelta(minutes=8))

        deleted = cleanup_idle_rooms()

        self.assertEqual(deleted, 1)
        self.assertFalse(Room.objects.filter(id=room.id).exists())
