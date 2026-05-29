from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Room",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("has_password", models.BooleanField(default=False)),
                ("password_hash", models.CharField(blank=True, max_length=256)),
                (
                    "rule_set",
                    models.CharField(
                        choices=[("standard", "无禁手"), ("renju", "有禁手")],
                        default="standard",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("waiting", "等待中"), ("playing", "进行中"), ("finished", "已结束")],
                        default="waiting",
                        max_length=20,
                    ),
                ),
                ("winner", models.CharField(blank=True, max_length=10)),
                ("max_players", models.PositiveSmallIntegerField(default=2)),
                (
                    "black_player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="black_rooms",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "white_player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="white_rooms",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Move",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("move_number", models.PositiveIntegerField()),
                ("x", models.PositiveSmallIntegerField()),
                ("y", models.PositiveSmallIntegerField()),
                ("color", models.CharField(choices=[("black", "黑棋"), ("white", "白棋")], max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="moves", to="game.room"),
                ),
            ],
            options={
                "ordering": ["move_number"],
                "constraints": [
                    models.UniqueConstraint(fields=("room", "move_number"), name="unique_room_move_number"),
                    models.UniqueConstraint(fields=("room", "x", "y"), name="unique_room_point"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_name", models.CharField(max_length=80)),
                ("text", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="game.room",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
