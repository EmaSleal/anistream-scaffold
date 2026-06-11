"""In-process TTL cache utility.

Thread-safe, per-key TTL backed by a plain dict.  No external dependencies.
Loss of cache on process restart is acceptable (see design ADR-6).
"""
import time
import threading
from typing import Any


class TTLCache:
    """Simple in-memory cache with per-key expiry.

    Keys are strings; values can be any JSON-serializable object.
    Uses ``time.monotonic()`` so TTL is immune to system-clock adjustments.
    The ``threading.Lock`` makes every operation safe under multi-threaded
    WSGI servers (gunicorn --threads, Werkzeug threaded=True).

    Note: each worker process keeps its own cache copy.  A cold miss simply
    recomputes the result; cross-worker sharing (Redis) is out of scope.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Return cached value for *key*, or ``None`` on miss / expiry."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* for the configured TTL."""
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        """Remove *key* from the cache (no-op if absent)."""
        with self._lock:
            self._store.pop(key, None)
