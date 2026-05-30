from threading import Lock

from django.contrib.auth.models import User

from .serializers import UserSerializer

_lock = Lock()
_connections_by_user = {}


def mark_online(user_id, channel_name):
    with _lock:
        channels = _connections_by_user.setdefault(user_id, set())
        channels.add(channel_name)


def mark_offline(user_id, channel_name):
    with _lock:
        channels = _connections_by_user.get(user_id)
        if not channels:
            return
        channels.discard(channel_name)
        if not channels:
            _connections_by_user.pop(user_id, None)


def online_user_ids():
    with _lock:
        return list(_connections_by_user.keys())


def online_users_payload():
    ids = online_user_ids()
    users = User.objects.filter(id__in=ids).order_by("username")
    return UserSerializer(users, many=True).data
