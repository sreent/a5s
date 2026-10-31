"""Circuit breakers: a model that fails three times in a row isn't called again for five
minutes, so runs stop quickly rather than each waiting for it to time out, and a5s tries it
again on its own, without anyone stepping in.

After the wait, one call goes through. If it works, the breaker closes; if not, the model
waits another five minutes. Each gateway keeps its own breakers, and the ledger records each
one opening and closing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

FAILURES = 3  # in a row, before a model isn't called for a while
WAIT = 300.0  # seconds before trying it again


@dataclass
class Breaker:
    failures: int = 0
    opened_at: float | None = None  # while it's open, when it opened, or last let a call through


@dataclass
class Breakers:
    clock: Callable[[], float] = time.monotonic
    _held: dict[str, Breaker] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, key: str) -> bool:
        """Whether to call it now: unless it's open, and it's not yet time to try it again."""
        with self._lock:
            held = self._held.get(key)
            if held is None or held.opened_at is None:
                return True
            if self.clock() - held.opened_at < WAIT:
                return False
            held.opened_at = self.clock()  # this call tries it: the rest wait for how it goes
            return True

    def worked(self, key: str) -> bool:
        """It answered. Whether that closed its breaker."""
        with self._lock:
            held = self._held.pop(key, None)
            return held is not None and held.opened_at is not None

    def failed(self, key: str) -> bool:
        """It failed. Whether that opened its breaker."""
        with self._lock:
            held = self._held.setdefault(key, Breaker())
            held.failures += 1
            if held.opened_at is None and held.failures >= FAILURES:
                held.opened_at = self.clock()
                return True
            return False

    def open(self) -> list[str]:
        """The models that aren't being called for now."""
        with self._lock:
            return sorted(k for k, b in self._held.items() if b.opened_at is not None)
