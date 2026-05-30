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
    max_players = models.PositiveSmallIntegerField(default=2)
    max_spectators = models.PositiveSmallIntegerField(default=4)
    black_ready = models.BooleanField(default=False)
    white_ready = models.BooleanField(default=False)
    last_activity_at = models.DateTimeField(default=timezone.now)

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
        elif self.winner:
            self.status = self.STATUS_FINISHED
        elif self.players_count == 2 and self.black_ready and self.white_ready:
            self.status = self.STATUS_PLAYING
        else:
            self.status = self.STATUS_WAITING

    def __str__(self):
        return self.name


class Move(models.Model):
    COLOR_BLACK = "black"
    COLOR_WHITE = "white"
    COLOR_CHOICES = (
        (COLOR_BLACK, "黑棋"),
        (COLOR_WHITE, "白棋"),
    )

    room = models.ForeignKey(Room, related_name="moves", on_delete=models.CASCADE)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    move_number = models.PositiveIntegerField()
    x = models.PositiveSmallIntegerField()
    y = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["move_number"]
        constraints = [
            models.UniqueConstraint(fields=["room", "move_number"], name="unique_room_move_number"),
            models.UniqueConstraint(fields=["room", "x", "y"], name="unique_room_point"),
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
