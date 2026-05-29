from django.contrib.auth.models import User
from django.test import TestCase

from .models import Room
from .rules import evaluate_move, validate_move
from .services import leave_room


class RuleEngineTests(TestCase):
    def test_standard_rule_allows_black_overline_as_win(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(5)]
        result = evaluate_move(stones, 5, 7, "black", Room.RULE_STANDARD)

        self.assertTrue(result.ok)
        self.assertEqual(result.winner, "black")

    def test_renju_blocks_black_overline(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(5)]
        result = validate_move(stones, 5, 7, "black", Room.RULE_RENJU)

        self.assertFalse(result.ok)
        self.assertTrue(result.forbidden)

    def test_renju_allows_exact_five_for_black(self):
        stones = [{"x": x, "y": 7, "color": "black"} for x in range(4)]
        result = evaluate_move(stones, 4, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertEqual(result.winner, "black")

    def test_renju_blocks_double_four_for_black(self):
        stones = [
            {"x": 5, "y": 7, "color": "black"},
            {"x": 6, "y": 7, "color": "black"},
            {"x": 8, "y": 7, "color": "black"},
            {"x": 7, "y": 5, "color": "black"},
            {"x": 7, "y": 6, "color": "black"},
            {"x": 7, "y": 8, "color": "black"},
        ]
        result = validate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertFalse(result.ok)
        self.assertTrue(result.forbidden)

    def test_renju_blocks_double_three_for_black(self):
        stones = [
            {"x": 6, "y": 7, "color": "black"},
            {"x": 8, "y": 7, "color": "black"},
            {"x": 7, "y": 6, "color": "black"},
            {"x": 7, "y": 8, "color": "black"},
        ]
        result = validate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertFalse(result.ok)
        self.assertTrue(result.forbidden)


class RoomLifecycleTests(TestCase):
    def test_last_player_leave_deletes_room(self):
        user = User.objects.create_user(username="alice", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=user)
        room.refresh_status()
        room.save()

        result = leave_room(room, user)

        self.assertIsNone(result)
        self.assertFalse(Room.objects.filter(id=room.id).exists())
