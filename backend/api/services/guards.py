"""Per-session coordination for the in-process, single-worker deployment.

* ``turn``   - only one NPC dialogue turn may be in flight per session (a second one gets
               409 instead of racing the first and producing an out-of-order history).
* ``commit`` - short critical section that serialises writes for one session, so the
               several state transitions of one dialogue turn are applied together.

The repository's revision check remains the source of truth for conflicts; these guards
only keep this API's own multi-step operations tidy. They do not work across processes.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from ..errors import ApiError

__all__ = ["SessionGuards"]


class SessionGuards:
    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._commit_locks: dict[str, threading.RLock] = {}
        self._active_turns: set[str] = set()

    @contextmanager
    def commit(self, session_id: str) -> Iterator[None]:
        with self._mutex:
            lock = self._commit_locks.setdefault(session_id, threading.RLock())
        with lock:
            yield

    @contextmanager
    def turn(self, session_id: str) -> Iterator[None]:
        with self._mutex:
            if session_id in self._active_turns:
                raise ApiError(
                    409,
                    "DIALOGUE_TURN_IN_PROGRESS",
                    "A conversation turn for this session is already being processed",
                )
            self._active_turns.add(session_id)
        try:
            yield
        finally:
            with self._mutex:
                self._active_turns.discard(session_id)

    def forget(self, session_id: str) -> None:
        with self._mutex:
            self._commit_locks.pop(session_id, None)
