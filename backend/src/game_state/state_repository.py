from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.contracts.dialogue import DialogueMessage
from shared.contracts.errors import (
    ContractValidationError,
    ResourceNotFoundError,
    StateConflictError,
)
from shared.contracts.game_state import GameState


@dataclass(frozen=True, slots=True)
class GameSession:
    """One player's saved game: the GameState plus the full dialogue history.

    Everything inside is immutable, so nobody can change a stored session
    by accident through a reference they were given.
    """

    state: GameState
    dialogue_history: tuple[DialogueMessage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state, GameState):
            raise TypeError(f"'state' must be a GameState, got {type(self.state).__name__}.")
        if not isinstance(self.dialogue_history, tuple):
            raise TypeError(
                f"'dialogue_history' must be a tuple, got {type(self.dialogue_history).__name__}."
            )

        seen_ids: set[str] = set()
        last_sequence: dict[str, int] = {}  # dialogue session id -> last sequence number
        for i, msg in enumerate(self.dialogue_history):
            name = f"'dialogue_history[{i}]'"
            if not isinstance(msg, DialogueMessage):
                raise TypeError(f"{name} must be a DialogueMessage, got {type(msg).__name__}.")
            if msg.case_id != self.state.case_id:
                raise ValueError(
                    f"{name} belongs to case {msg.case_id!r}, expected {self.state.case_id!r}."
                )
            if msg.message_id in seen_ids:
                raise ValueError(
                    f"'dialogue_history' contains duplicate message ID: {msg.message_id!r}."
                )
            seen_ids.add(msg.message_id)

            previous = last_sequence.get(msg.session_id)
            if previous is not None and msg.sequence_number <= previous:
                raise ValueError(
                    f"{name} has sequence {msg.sequence_number} after {previous} "
                    f"in dialogue session {msg.session_id!r}."
                )
            last_sequence[msg.session_id] = msg.sequence_number

    @property
    def game_id(self) -> str:
        return self.state.game_id

    @property
    def revision(self) -> int:
        return self.state.revision


class GameStateRepository(ABC):
    """Where sessions are stored. Swap the implementation for Redis/PostgreSQL later."""

    @abstractmethod
    def create(self, session: GameSession) -> None:
        """Store a new session. Raises StateConflictError if the ID already exists."""

    @abstractmethod
    def get(self, game_id: str) -> GameSession:
        """Return the session. Raises ResourceNotFoundError if the ID is unknown."""

    @abstractmethod
    def save(self, session: GameSession, expected_revision: int) -> None:
        """Replace the stored session (optimistic concurrency).

        Only works if the stored revision is `expected_revision` and the new
        session's revision is exactly `expected_revision + 1`.
        """

    @abstractmethod
    def delete(self, game_id: str) -> None:
        """Remove the session. Raises ResourceNotFoundError if the ID is unknown."""


class InMemoryGameStateRepository(GameStateRepository):
    """Thread-safe repository that keeps sessions in a dict (lost on restart)."""

    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._lock = threading.Lock()

    def create(self, session: GameSession) -> None:
        _check_is_session(session)
        with self._lock:
            if session.game_id in self._sessions:
                raise StateConflictError(
                    "A game session with this ID already exists.",
                    details=(session.game_id,),
                    code="GAME_SESSION_EXISTS",
                )
            self._sessions[session.game_id] = session

    def get(self, game_id: str) -> GameSession:
        with self._lock:
            return self._find(game_id)

    def save(self, session: GameSession, expected_revision: int) -> None:
        _check_is_session(session)
        with self._lock:
            stored = self._find(session.game_id)

            if stored.revision != expected_revision:
                raise StateConflictError(
                    "Game session was modified concurrently.",
                    details=(
                        f"expected revision {expected_revision}, stored revision {stored.revision}",
                    ),
                    code="REVISION_CONFLICT",
                )
            if session.revision != expected_revision + 1:
                raise ContractValidationError(
                    "A save must advance the revision by exactly one.",
                    details=(f"expected {expected_revision + 1}, got {session.revision}",),
                    code="REVISION_INVALID",
                )
            if session.state.case_id != stored.state.case_id:
                raise ContractValidationError(
                    "A session cannot change its case.", code="SESSION_CASE_CHANGED"
                )
            old_history = stored.dialogue_history
            if session.dialogue_history[: len(old_history)] != old_history:
                raise ContractValidationError(
                    "Dialogue history is append-only.", code="DIALOGUE_HISTORY_REWRITTEN"
                )

            self._sessions[session.game_id] = session

    def delete(self, game_id: str) -> None:
        with self._lock:
            self._find(game_id)  # raises if the session does not exist
            del self._sessions[game_id]

    def _find(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except (KeyError, TypeError):  # TypeError: unhashable id such as a list
            raise ResourceNotFoundError(
                f"Unknown game session: {game_id!r}.", code="GAME_SESSION_NOT_FOUND"
            ) from None


def _check_is_session(session: object) -> None:
    if not isinstance(session, GameSession):
        raise TypeError(f"'session' must be a GameSession, got {type(session).__name__}.")
