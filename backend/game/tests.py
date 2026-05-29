from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Room
from .rules import evaluate_move
from .services import leave_room


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
    def test_last_player_leave_deletes_room(self):
        user = User.objects.create_user(username="alice", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=user)
        room.refresh_status()
        room.save()

        result = leave_room(room, user)

        self.assertIsNone(result)
        self.assertFalse(Room.objects.filter(id=room.id).exists())
