from threading import RLock
from time import monotonic
from typing import Any, Callable

from app.config import settings


class UserCache:
    """Small process-local TTL cache. The interface can later be backed by Redis."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def key(user_id: str, resource: str, suffix: str = "") -> str:
        return f"user:{user_id}:{resource}:{suffix}"

    def get_or_set(self, key: str, loader: Callable[[], Any]) -> Any:
        with self._lock:
            item = self._items.get(key)
            if item and item[0] > monotonic():
                return item[1]
        value = loader()
        with self._lock:
            self._items[key] = (monotonic() + settings.cache_ttl_seconds, value)
        return value

    def invalidate_user(self, user_id: str) -> None:
        prefix = f"user:{user_id}:"
        with self._lock:
            self._items = {key: value for key, value in self._items.items() if not key.startswith(prefix)}


cache = UserCache()
