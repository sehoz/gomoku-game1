from datetime import timedelta
from threading import Lock

from django.contrib.auth.models import User
from django.utils import timezone

from .models import PlayerProfile
from .serializers import UserSerializer

_lock = Lock()
_connections_by_user = {}
ONLINE_WINDOW_SECONDS = 45


def mark_online(user_id, channel_name):
    with _lock:
        channels = _connections_by_user.setdefault(user_id, set())
        channels.add(channel_name)
    touch_user(user_id)


def mark_offline(user_id, channel_name):
    with _lock:
        channels = _connections_by_user.get(user_id)
        if not channels:
            return
        channels.discard(channel_name)
        if not channels:
            _connections_by_user.pop(user_id, None)


def touch_user(user_id):
    PlayerProfile.objects.update_or_create(user_id=user_id, defaults={"last_seen_at": timezone.now()})


def online_user_ids():
    with _lock:
        connected_ids = set(_connections_by_user.keys())
    cutoff = timezone.now() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    recent_ids = set(PlayerProfile.objects.filter(last_seen_at__gte=cutoff).values_list("user_id", flat=True))
    return list(connected_ids | recent_ids)


def online_users_payload():
    ids = online_user_ids()
    users = User.objects.filter(id__in=ids, is_active=True, is_staff=False, is_superuser=False).order_by("username")
    return UserSerializer(users, many=True).data
