from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .ai import choose_ai_move
from .models import GameSession, HiddenMatchRecord, Move, PlayerProfile, Room, SpectatorSeat
from .rules import evaluate_move
from .services import (
    SeatSwitchNeedsConsent,
    accept_seat_switch,
    add_chat,
    cleanup_idle_rooms,
    create_room_invitation,
    decode_pending_request,
    join_room,
    kick_user,
    leave_room,
    make_move,
    respond_room_invitation,
    set_ready,
    surrender,
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

    def test_update_profile_and_change_password(self):
        user = User.objects.create_user(username="alice", password="gomoku123")
        client = APIClient()
        client.force_authenticate(user)

        profile_response = client.patch("/api/profile/", {"username": "alice2", "avatar_url": "data:image/png;base64,abc"}, format="json")
        bad_password = client.post(
            "/api/profile/password/",
            {"old_password": "wrong", "new_password": "newpass123", "confirm_password": "newpass123"},
            format="json",
        )
        password_response = client.post(
            "/api/profile/password/",
            {"old_password": "gomoku123", "new_password": "newpass123", "confirm_password": "newpass123"},
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(user.username, "alice2")
        self.assertEqual(user.player_profile.avatar_data_url, "data:image/png;base64,abc")
        self.assertEqual(bad_password.status_code, 400)
        self.assertEqual(password_response.status_code, 200)
        self.assertTrue(User.objects.get(id=user.id).check_password("newpass123"))

    def test_online_users_include_recent_profile_activity(self):
        user = User.objects.create_user(username="alice", password="gomoku123")
        admin = User.objects.create_superuser(username="boss", password="gomoku123")
        PlayerProfile.objects.update_or_create(user=user, defaults={"last_seen_at": timezone.now()})
        PlayerProfile.objects.update_or_create(user=admin, defaults={"last_seen_at": timezone.now()})

        response = APIClient().get("/api/online/")

        self.assertEqual(response.status_code, 200)
        usernames = [item["username"] for item in response.data["users"]]
        self.assertIn("alice", usernames)
        self.assertNotIn("boss", usernames)

    def test_seeded_admin_can_use_admin_endpoints(self):
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.check_password("admin123321"))
        client = APIClient()
        client.force_authenticate(admin)

        create_response = client.post("/api/admin/users/", {"username": "managed", "password": "gomoku123"}, format="json")
        list_response = client.get("/api/admin/users/")
        room = Room.objects.create(name="后台房间")
        rooms_response = client.get("/api/admin/rooms/")
        delete_response = client.delete(f"/api/admin/rooms/{room.id}/")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(rooms_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)


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

    def test_renju_black_double_jump_three_loses(self):
        stones = [
            {"x": 5, "y": 7, "color": "black"},
            {"x": 9, "y": 7, "color": "black"},
            {"x": 7, "y": 5, "color": "black"},
            {"x": 7, "y": 9, "color": "black"},
        ]
        result = evaluate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertTrue(result.forbidden)
        self.assertEqual(result.winner, "white")

    def test_renju_black_diagonal_far_jump_double_three_loses(self):
        stones = [
            {"x": 4, "y": 4, "color": "black"},
            {"x": 6, "y": 6, "color": "black"},
            {"x": 9, "y": 9, "color": "black"},
            {"x": 4, "y": 10, "color": "black"},
            {"x": 6, "y": 8, "color": "black"},
            {"x": 9, "y": 5, "color": "black"},
        ]
        result = evaluate_move(stones, 7, 7, "black", Room.RULE_RENJU)

        self.assertTrue(result.ok)
        self.assertTrue(result.forbidden)
        self.assertEqual(result.winner, "white")


class RoomLifecycleTests(TestCase):
    def playable_room(self, black, white):
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)
        set_ready(room, black, True)
        set_ready(room, white, True)
        room.refresh_from_db()
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

    def test_undo_request_is_visible_in_room_state(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        make_move(room, black, 7, 7)
        client = APIClient()
        client.force_authenticate(black)

        response = client.post(f"/api/rooms/{room.id}/undo/request/", {}, format="json")
        state = client.get(f"/api/rooms/{room.id}/state/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state.data["room"]["pending_undo_request"]["username"], "black")

    def test_undo_after_opponent_response_removes_two_stones(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        make_move(room, black, 7, 7)
        make_move(room, white, 7, 8)

        _room, removed = undo_last_turn(room, black)

        self.assertEqual(removed, 2)
        self.assertEqual(room.moves.count(), 0)

    def test_each_player_has_three_successful_undos_per_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)

        for x in range(3):
            make_move(room, black, x, 7)
            undo_last_turn(room, black)
        make_move(room, black, 4, 7)

        with self.assertRaisesMessage(ValueError, "本局悔棋次数已用完"):
            undo_last_turn(room, black)

    def test_room_name_must_be_unique_among_active_rooms(self):
        owner = User.objects.create_user(username="owner", password="gomoku123")
        Room.objects.create(name="好友对局", black_player=owner)
        client = APIClient()
        client.force_authenticate(owner)

        response = client.post("/api/rooms/", {"name": "好友对局", "rule_set": "standard"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "房间名重复")

    def test_create_room_accepts_time_controls(self):
        owner = User.objects.create_user(username="owner", password="gomoku123")
        client = APIClient()
        client.force_authenticate(owner)

        response = client.post(
            "/api/rooms/",
            {"name": "计时房", "rule_set": "standard", "move_time_seconds": 60, "total_time_seconds": 900},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["move_time_seconds"], 60)
        self.assertEqual(response.data["total_time_seconds"], 900)

    def test_create_room_accepts_unlimited_time_controls(self):
        owner = User.objects.create_user(username="owner", password="gomoku123")
        client = APIClient()
        client.force_authenticate(owner)

        response = client.post(
            "/api/rooms/",
            {"name": "不限时房", "rule_set": "standard", "move_time_seconds": 0, "total_time_seconds": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["move_time_seconds"], 0)
        self.assertEqual(response.data["total_time_seconds"], 0)

    def test_host_can_update_room_settings(self):
        host = User.objects.create_user(username="host", password="gomoku123")
        room = Room.objects.create(name="旧房间", black_player=host, host=host)
        client = APIClient()
        client.force_authenticate(host)

        response = client.patch(
            f"/api/rooms/{room.id}/settings/",
            {
                "name": "新房间",
                "rule_set": "renju",
                "move_time_seconds": 0,
                "total_time_seconds": 0,
                "has_password": True,
                "password": "1",
            },
            format="json",
        )

        room.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "新房间")
        self.assertEqual(response.data["rule_set"], "renju")
        self.assertEqual(response.data["move_time_seconds"], 0)
        self.assertEqual(response.data["total_time_seconds"], 0)
        self.assertTrue(room.password_matches("1"))

    def test_non_host_cannot_update_room_settings(self):
        host = User.objects.create_user(username="host", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=host, white_player=white, host=host)
        client = APIClient()
        client.force_authenticate(white)

        response = client.patch(f"/api/rooms/{room.id}/settings/", {"name": "非法修改"}, format="json")

        self.assertEqual(response.status_code, 403)

    def test_create_room_accepts_short_room_password(self):
        owner = User.objects.create_user(username="owner", password="gomoku123")
        client = APIClient()
        client.force_authenticate(owner)

        response = client.post(
            "/api/rooms/",
            {"name": "短口令房", "rule_set": "standard", "has_password": True, "password": "1"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["has_password"])

    def test_room_state_polling_refreshes_player_seen_time(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        old_seen = timezone.now() - timedelta(minutes=8)
        room = Room.objects.create(
            name="测试房间",
            black_player=black,
            white_player=white,
            black_last_seen_at=old_seen,
            white_last_seen_at=old_seen,
        )
        client = APIClient()
        client.force_authenticate(black)

        response = client.get(f"/api/rooms/{room.id}/state/")

        self.assertEqual(response.status_code, 200)
        room.refresh_from_db()
        self.assertGreater(room.black_last_seen_at, old_seen)

    def test_room_state_returns_player_avatar_urls(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        PlayerProfile.objects.update_or_create(user=black, defaults={"avatar_data_url": "data:image/png;base64,black"})
        PlayerProfile.objects.update_or_create(user=white, defaults={"avatar_data_url": "data:image/png;base64,white"})
        room = Room.objects.create(name="avatar-room", black_player=black, white_player=white)
        client = APIClient()
        client.force_authenticate(black)

        response = client.get(f"/api/rooms/{room.id}/state/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["room"]["black_player_avatar_url"], "data:image/png;base64,black")
        self.assertEqual(response.data["room"]["white_player_avatar_url"], "data:image/png;base64,white")

    def test_host_transfers_to_next_joined_player_when_host_leaves(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(
            name="测试房间",
            black_player=black,
            white_player=white,
            host=black,
            black_joined_at=timezone.now() - timedelta(minutes=2),
            white_joined_at=timezone.now() - timedelta(minutes=1),
        )

        result = leave_room(room, black)

        self.assertIsNotNone(result)
        result.refresh_from_db()
        self.assertEqual(result.host, white)

    def test_host_can_kick_room_member(self):
        host = User.objects.create_user(username="host", password="gomoku123")
        target = User.objects.create_user(username="target", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=host, white_player=target, host=host)

        result = kick_user(room, host, target.id)

        self.assertIsNotNone(result)
        result.refresh_from_db()
        self.assertIsNone(result.white_player)

    def test_invitation_accept_joins_room(self):
        host = User.objects.create_user(username="host", password="gomoku123")
        invitee = User.objects.create_user(username="invitee", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=host, host=host)
        invitation = create_room_invitation(room, host, invitee)

        joined_room, handled = respond_room_invitation(invitation, invitee, True)

        self.assertEqual(handled.status, "accepted")
        self.assertEqual(joined_room.white_player, invitee)

    def test_surrender_finishes_active_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        make_move(room, black, 7, 7)

        result = surrender(room, white)

        result.refresh_from_db()
        game = result.current_game
        self.assertEqual(result.status, Room.STATUS_WAITING)
        self.assertEqual(game.status, GameSession.STATUS_FINISHED)
        self.assertEqual(game.winner, "black")
        self.assertEqual(game.end_reason, "surrender")

    def test_leaderboard_orders_by_wins(self):
        alice = User.objects.create_user(username="alice", password="gomoku123")
        bob = User.objects.create_user(username="bob", password="gomoku123")
        PlayerProfile.objects.update_or_create(user=alice, defaults={"avatar_data_url": "data:image/png;base64,alice"})
        game = GameSession.objects.create(
            room_name="测试房间",
            black_player=alice,
            white_player=bob,
            status=GameSession.STATUS_FINISHED,
            winner="black",
            ended_at=timezone.now(),
        )
        Move.objects.create(game=game, player=alice, move_number=1, x=7, y=7, color="black")

        response = APIClient().get("/api/leaderboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["entries"][0]["user"]["username"], "alice")
        self.assertEqual(response.data["entries"][0]["user"]["avatar_url"], "data:image/png;base64,alice")
        self.assertEqual(response.data["entries"][0]["wins"], 1)

    def test_match_detail_returns_replay_moves(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        game = GameSession.objects.create(
            room_name="测试房间",
            black_player=black,
            white_player=white,
            status=GameSession.STATUS_FINISHED,
            winner="black",
            ended_at=timezone.now(),
        )
        Move.objects.create(game=game, player=black, move_number=1, x=7, y=7, color="black")
        client = APIClient()
        client.force_authenticate(black)

        response = client.get(f"/api/profile/matches/{game.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["moves"][0]["move_number"], 1)

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
        self.assertEqual(GameSession.objects.count(), 1)

    def test_second_move_by_white_is_persisted_through_api(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        black_client = APIClient()
        white_client = APIClient()
        black_client.force_authenticate(black)
        white_client.force_authenticate(white)

        first = black_client.post(f"/api/rooms/{room.id}/move/", {"x": 7, "y": 7}, format="json")
        second = white_client.post(f"/api/rooms/{room.id}/move/", {"x": 7, "y": 8}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(GameSession.objects.get(id=room.current_game_id).moves.count(), 2)

    def test_start_game_persists_both_ready_flags(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)

        set_ready(room, black, True)
        set_ready(room, white, True)
        room.refresh_from_db()

        self.assertEqual(room.status, Room.STATUS_PLAYING)
        self.assertTrue(room.black_ready)
        self.assertTrue(room.white_ready)

    def test_finished_game_is_logged_without_deleting_room(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)

        for x in range(4):
            make_move(room, black, x, 0)
            make_move(room, white, x, 1)
        make_move(room, black, 4, 0)
        room.refresh_from_db()
        game = room.current_game

        self.assertTrue(Room.objects.filter(id=room.id).exists())
        self.assertEqual(room.status, Room.STATUS_WAITING)
        self.assertEqual(game.status, GameSession.STATUS_FINISHED)
        self.assertEqual(game.winner, "black")
        self.assertIsNotNone(game.ended_at)

    def test_finished_game_swaps_black_and_white_seats_for_next_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)

        for x in range(4):
            make_move(room, black, x, 0)
            make_move(room, white, x, 1)
        make_move(room, black, 4, 0)

        room.refresh_from_db()
        game = room.current_game
        self.assertEqual(game.black_player, black)
        self.assertEqual(game.white_player, white)
        self.assertEqual(room.black_player, white)
        self.assertEqual(room.white_player, black)
        self.assertFalse(room.black_ready)
        self.assertFalse(room.white_ready)

    def test_profile_match_history_uses_game_sessions(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        for x in range(4):
            make_move(room, black, x, 0)
            make_move(room, white, x, 1)
        make_move(room, black, 4, 0)
        client = APIClient()
        client.force_authenticate(black)

        response = client.get("/api/profile/matches/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["records"][0]["room_name"], "测试房间")
        self.assertEqual(response.data["records"][0]["result"], "win")

    def test_profile_match_history_is_paginated_by_ten(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        for index in range(12):
            game = GameSession.objects.create(
                room_name=f"第{index}局",
                black_player=black,
                white_player=white,
                status=GameSession.STATUS_FINISHED,
                winner="black",
                started_at=timezone.now() - timedelta(minutes=20 - index),
                ended_at=timezone.now() - timedelta(minutes=19 - index),
            )
            Move.objects.create(game=game, player=black, move_number=1, x=7, y=7, color="black")
        client = APIClient()
        client.force_authenticate(black)

        first = client.get("/api/profile/matches/?page=1")
        second = client.get("/api/profile/matches/?page=2")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["records"]), 10)
        self.assertEqual(first.data["total"], 12)
        self.assertEqual(first.data["total_pages"], 2)
        self.assertEqual(len(second.data["records"]), 2)

    def test_player_can_hide_own_match_record_without_deleting_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        game = GameSession.objects.create(
            room_name="hidden-room",
            black_player=black,
            white_player=white,
            status=GameSession.STATUS_FINISHED,
            winner="black",
            ended_at=timezone.now(),
        )
        Move.objects.create(game=game, player=black, move_number=1, x=7, y=7, color="black")
        client = APIClient()
        client.force_authenticate(black)

        delete_response = client.delete(f"/api/profile/matches/{game.id}/")
        history_response = client.get("/api/profile/matches/")
        replay_response = client.get(f"/api/profile/matches/{game.id}/")
        public_response = APIClient().get(f"/api/users/{black.id}/")

        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(HiddenMatchRecord.objects.filter(user=black, game=game).exists())
        self.assertTrue(GameSession.objects.filter(id=game.id).exists())
        self.assertEqual(history_response.data["records"], [])
        self.assertEqual(replay_response.status_code, 404)
        self.assertEqual(public_response.data["user"]["recent_matches"], [])

    def test_zero_move_ready_session_is_not_logged(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)

        leave_room(room, black)
        client = APIClient()
        client.force_authenticate(black)
        response = client.get("/api/profile/matches/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["records"], [])
        self.assertFalse(GameSession.objects.exists())
        self.assertTrue(Room.objects.filter(id=room.id).exists())

    def test_turn_timeout_finishes_current_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(
            name="计时房",
            black_player=black,
            white_player=white,
            move_time_seconds=10,
            total_time_seconds=60,
        )
        set_ready(room, black, True)
        set_ready(room, white, True)
        room.refresh_from_db()
        make_move(room, black, 7, 7)
        game = room.current_game
        GameSession.objects.filter(id=game.id).update(turn_started_at=timezone.now() - timedelta(seconds=11))

        _room, result = make_move(room, white, 7, 8)

        room.refresh_from_db()
        game.refresh_from_db()
        self.assertEqual(result.winner, "black")
        self.assertEqual(result.reason, "对局已因走棋超时结束")
        self.assertEqual(room.status, Room.STATUS_WAITING)
        self.assertEqual(game.status, GameSession.STATUS_FINISHED)
        self.assertEqual(game.winner, "black")
        self.assertEqual(game.end_reason, "time")

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

    def test_seat_switch_request_is_persisted_for_polling(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = Room.objects.create(name="测试房间", black_player=black, white_player=white)
        client = APIClient()
        client.force_authenticate(black)

        response = client.post(f"/api/rooms/{room.id}/switch-seat/", {"target_seat": "white"}, format="json")
        room.refresh_from_db()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(decode_pending_request(room.pending_seat_switch_request)["requester_username"], "black")

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

    @override_settings(ROOM_IDLE_MINUTES=5)
    def test_cleanup_idle_waiting_room_even_after_finished_game(self):
        black = User.objects.create_user(username="black", password="gomoku123")
        white = User.objects.create_user(username="white", password="gomoku123")
        room = self.playable_room(black, white)
        for x in range(4):
            make_move(room, black, x, 0)
            make_move(room, white, x, 1)
        make_move(room, black, 4, 0)
        Room.objects.filter(id=room.id).update(last_activity_at=timezone.now() - timedelta(minutes=8))

        deleted = cleanup_idle_rooms()

        self.assertEqual(deleted, 1)
        self.assertFalse(Room.objects.filter(id=room.id).exists())
        self.assertEqual(GameSession.objects.count(), 1)
        self.assertEqual(GameSession.objects.first().moves.count(), 9)
