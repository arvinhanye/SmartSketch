"""Bounded waits for observable test conditions (never a fixed startup delay)."""

from __future__ import annotations

import time
from threading import Event
from typing import Callable, TypeVar

T = TypeVar("T")


def wait_until(
    predicate: Callable[[], T],
    *,
    timeout: float,
    interval: float = 0.01,
    description: str = "condition",
) -> T:
    """Return the first truthy result or fail with the awaited condition's name.

    Predicates must bound their own I/O and handle only expected transient errors;
    unexpected exceptions propagate instead of becoming misleading timeout errors.
    """
    if timeout < 0 or interval <= 0:
        raise ValueError("timeout must be non-negative and interval must be positive")
    deadline = time.monotonic() + timeout
    pause = Event()
    while True:
        result = predicate()
        if result:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Timed out after {timeout:g}s waiting for {description}")
        pause.wait(min(interval, remaining))
