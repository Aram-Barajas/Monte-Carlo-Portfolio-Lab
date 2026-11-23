"""Bounded, thread-safe cache for historical market prices."""

from collections import OrderedDict
from concurrent.futures import Future
from threading import Lock
from time import monotonic


class MarketDataCache:
    def __init__(self, max_entries=32, ttl_seconds=900, clock=monotonic):
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError(
                "Cache size and expiration must be positive."
            )

        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.entries = OrderedDict()
        self.pending = {}
        self.lock = Lock()

    def get(self, key):
        """Return a copy of fresh prices, or None on a cache miss."""

        with self.lock:
            prices = self._fresh_locked(key)
            return prices.copy(deep=True) if prices is not None else None

    def _fresh_locked(self, key):
        if key not in self.entries:
            return None
        expires, prices = self.entries[key]
        if self.clock() >= expires:
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return prices

    def get_or_load(self, key, loader):
        """Coalesce concurrent misses for the same key; don't cache failures."""
        with self.lock:
            prices = self._fresh_locked(key)
            if prices is not None:
                return prices.copy(deep=True)
            future = self.pending.get(key)
            leader = future is None
            if leader:
                future = self.pending[key] = Future()
        if not leader:
            return future.result().copy(deep=True)
        try:
            prices = loader()
            snapshot = prices.copy(deep=True)
            self.put(key, prices)
            future.set_result(snapshot)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)
        return snapshot.copy(deep=True)

    def put(self, key, prices):
        """Store an isolated copy and evict least recently used entries."""

        with self.lock:
            now = self.clock()

            for expired_key, (expires, _) in list(self.entries.items()):
                if expires <= now:
                    del self.entries[expired_key]

            self.entries[key] = (
                now + self.ttl_seconds,
                prices.copy(deep=True)
            )

            self.entries.move_to_end(key)

            while len(self.entries) > self.max_entries:
                self.entries.popitem(last=False)
