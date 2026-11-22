"""Bounded, thread-safe cache for historical market prices."""

from collections import OrderedDict
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
        self.lock = Lock()

    def get(self, key):
        """Return a copy of fresh prices, or None on a cache miss."""

        with self.lock:
            if key not in self.entries:
                return None

            expires, prices = self.entries[key]

            if self.clock() >= expires:
                del self.entries[key]
                return None

            self.entries.move_to_end(key)

            return prices.copy(deep=True)

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