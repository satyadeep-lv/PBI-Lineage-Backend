from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative.")
        if max_entries < 1:
            raise ValueError("max_entries must be positive.")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self.clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: K, value: V) -> None:
        if self.ttl_seconds == 0:
            return
        with self._lock:
            self._entries[key] = (self.clock() + self.ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, predicate: Callable[[K], bool] | None = None) -> None:
        with self._lock:
            if predicate is None:
                self._entries.clear()
                return
            for key in list(self._entries):
                if predicate(key):
                    del self._entries[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
