"""Terminal, process-local lease cutoff (task-processing §8.2/§8.5)."""

from collections.abc import Callable
import math
import threading
import time

from app.repositories.task_leases import LeaseLost


class LeaseGuard:
    def __init__(self, lease_seconds: int, *, last_success: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if type(lease_seconds) is not int or lease_seconds < 1:
            raise ValueError('lease_seconds must be a positive integer')
        if not math.isfinite(last_success):
            raise ValueError('last_success must be finite')
        self._window = lease_seconds - lease_seconds / 3
        self._deadline = last_success + self._window
        self._clock = clock
        self._mutex = threading.Lock()
        self.lost = threading.Event()

    @classmethod
    def from_expiry(cls, lease_seconds: int, expires_at: int) -> 'LeaseGuard':
        # SQLite's integer expiration rounds down; do not grant a fresh TTL at
        # object construction, nor count time already spent since acquisition.
        started = time.monotonic() - max(0.0, lease_seconds - (expires_at - time.time()))
        return cls(lease_seconds, last_success=started)

    def _remaining(self) -> float:
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            self.lost.set()
        if self.lost.is_set():
            raise LeaseLost('local lease cutoff reached')
        return remaining

    def check(self) -> None:
        self.remaining()

    def remaining(self) -> float:
        with self._mutex:
            return self._remaining()

    def renewed(self, started: float) -> None:
        with self._mutex:
            try:
                self._remaining()  # A late reply never revives a terminal guard.
            except LeaseLost:
                return
            self._deadline = max(self._deadline, started + self._window)

    def lose(self) -> None:
        self.lost.set()
