from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class Room(models.Model):
    RULE_STANDARD = "standard"
    RULE_RENJU = "renju"
    RULE_CHOICES = (
        (RULE_STANDARD, "无禁手"),
        (RULE_RENJU, "有禁手"),
    )

    STATUS_WAITING = "waiting"
    STATUS_PLAYING = "playing"
    STATUS_FINISHED = "finished"
    STATUS_CHOICES = (
        (STATUS_WAITING, "等待中"),
        (STATUS_PLAYING, "进行中"),
        (STATUS_FINISHED, "已结束"),
    )

    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    has_password = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=256, blank=True)
    rule_set = models.CharField(max_length=20, choices=RULE_CHOICES, default=RULE_STANDARD)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="black_rooms",
        on_delete=models.SET_NULL,
    )
    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="white_rooms",
        on_delete=models.SET_NULL,
    )
    winner = models.CharField(max_length=10, blank=True)
    current_game = models.ForeignKey(
        "GameSession",
        null=True,
        blank=True,
        related_name="current_room",
        on_delete=models.SET_NULL,
    )
    max_players = models.PositiveSmallIntegerField(default=2)
    max_spectators = models.PositiveSmallIntegerField(default=4)
    move_time_seconds = models.PositiveSmallIntegerField(default=30)
    total_time_seconds = models.PositiveIntegerField(default=600)
    black_ready = models.BooleanField(default=False)
    white_ready = models.BooleanField(default=False)
    black_last_seen_at = models.DateTimeField(null=True, blank=True)
    white_last_seen_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    pending_undo_request = models.TextField(blank=True)
    pending_seat_switch_request = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def players_count(self):
        return int(bool(self.black_player_id)) + int(bool(self.white_player_id))

    @property
    def spectators_count(self):
        return self.spectators.count() if self.pk else 0

    @property
    def occupants_count(self):
        return self.players_count + self.spectators_count

    def set_password(self, raw_password):
        self.has_password = bool(raw_password)
        self.password_hash = make_password(raw_password) if raw_password else ""

    def password_matches(self, raw_password):
        if not self.has_password:
            return True
        return check_password(raw_password or "", self.password_hash)

    def refresh_status(self):
        if self.occupants_count == 0:
            self.status = self.STATUS_FINISHED
        elif self.current_game_id and self.current_game.status == GameSession.STATUS_PLAYING:
            self.status = self.STATUS_PLAYING
        else:
            self.status = self.STATUS_WAITING

    def __str__(self):
        return self.name


class GameSession(models.Model):
    STATUS_PLAYING = "playing"
    STATUS_FINISHED = "finished"
    STATUS_CHOICES = (
        (STATUS_PLAYING, "进行中"),
        (STATUS_FINISHED, "已结束"),
    )

    room = models.ForeignKey(Room, null=True, blank=True, related_name="games", on_delete=models.SET_NULL)
    room_name = models.CharField(max_length=80)
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="black_games",
        on_delete=models.SET_NULL,
    )
    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="white_games",
        on_delete=models.SET_NULL,
    )
    rule_set = models.CharField(max_length=20, choices=Room.RULE_CHOICES, default=Room.RULE_STANDARD)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLAYING)
    winner = models.CharField(max_length=10, blank=True)
    end_reason = models.CharField(max_length=40, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    black_undo_used = models.PositiveSmallIntegerField(default=0)
    white_undo_used = models.PositiveSmallIntegerField(default=0)
    move_time_seconds = models.PositiveSmallIntegerField(default=30)
    total_time_seconds = models.PositiveIntegerField(default=600)
    black_time_left_seconds = models.PositiveIntegerField(default=600)
    white_time_left_seconds = models.PositiveIntegerField(default=600)
    turn_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class Move(models.Model):
    COLOR_BLACK = "black"
    COLOR_WHITE = "white"
    COLOR_CHOICES = (
        (COLOR_BLACK, "黑棋"),
        (COLOR_WHITE, "白棋"),
    )

    room = models.ForeignKey(Room, null=True, blank=True, related_name="moves", on_delete=models.SET_NULL)
    game = models.ForeignKey(GameSession, related_name="moves", null=True, blank=True, on_delete=models.CASCADE)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    move_number = models.PositiveIntegerField()
    x = models.PositiveSmallIntegerField()
    y = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["move_number"]
        constraints = [
            models.UniqueConstraint(fields=["game", "move_number"], name="unique_game_move_number"),
            models.UniqueConstraint(fields=["game", "x", "y"], name="unique_game_point"),
        ]


class ChatMessage(models.Model):
    room = models.ForeignKey(Room, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    sender_name = models.CharField(max_length=80)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class SpectatorSeat(models.Model):
    room = models.ForeignKey(Room, related_name="spectators", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="spectator_seats", on_delete=models.CASCADE)
    seat_number = models.PositiveSmallIntegerField()
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seat_number"]
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="unique_room_spectator_user"),
            models.UniqueConstraint(fields=["room", "seat_number"], name="unique_room_spectator_seat"),
        ]
