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

__all__ = ["GameSession", "GameStateRepository", "InMemoryGameStateRepository"]


@dataclass(frozen=True, slots=True)
class GameSession:
    """One player's stored session: the ``GameState`` plus the full dialogue history.

    Both parts are immutable (frozen dataclass, tuples), so a stored session can
    never be changed through a reference handed to a caller.
    """

    state: GameState
    dialogue_history: tuple[DialogueMessage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state, GameState):
            raise TypeError(
                f"'state' must be a GameState, got {type(self.state).__name__}."
            )
        if not isinstance(self.dialogue_history, tuple):
            raise TypeError(
                "'dialogue_history' must be a tuple, "
                f"got {type(self.dialogue_history).__name__}."
            )
        seen: set[str] = set()
        last_sequence: dict[str, int] = {}
        for index, message in enumerate(self.dialogue_history):
            if not isinstance(message, DialogueMessage):
                raise TypeError(
                    f"'dialogue_history[{index}]' must be a DialogueMessage, "
                    f"got {type(message).__name__}."
                )
            if message.case_id != self.state.case_id:
                raise ValueError(
                    f"'dialogue_history[{index}]' belongs to case "
                    f"{message.case_id!r}, expected {self.state.case_id!r}."
                )
            if message.message_id in seen:
                raise ValueError(
                    f"'dialogue_history' contains duplicate message ID: "
                    f"{message.message_id!r}."
                )
            seen.add(message.message_id)
            previous = last_sequence.get(message.session_id)
            if previous is not None and message.sequence_number <= previous:
                raise ValueError(
                    f"'dialogue_history[{index}]' has sequence "
                    f"{message.sequence_number} after {previous} in dialogue "
                    f"session {message.session_id!r}."
                )
            last_sequence[message.session_id] = message.sequence_number

    @property
    def game_id(self) -> str:
        return self.state.game_id

    @property
    def revision(self) -> int:
        return self.state.revision


class GameStateRepository(ABC):
    """Storage port. Implementations may be swapped for Redis or PostgreSQL."""

    @abstractmethod
    def create(self, session: GameSession) -> None:
        """Store a new session. Raises ``StateConflictError`` if the ID exists."""

    @abstractmethod
    def get(self, game_id: str) -> GameSession:
        """Return the session. Raises ``ResourceNotFoundError`` if unknown."""

    @abstractmethod
    def save(self, session: GameSession, expected_revision: int) -> None:
        """Replace the stored session atomically (optimistic concurrency).

        Succeeds only if the stored revision equals ``expected_revision`` and
        the new session's revision is exactly ``expected_revision + 1``.
        """

    @abstractmethod
    def delete(self, game_id: str) -> None:
        """Remove the session. Raises ``ResourceNotFoundError`` if unknown."""


class InMemoryGameStateRepository(GameStateRepository):
    """Thread-safe in-memory repository holding immutable sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._lock = threading.Lock()

    def create(self, session: GameSession) -> None:
        if not isinstance(session, GameSession):
            raise TypeError(
                f"'session' must be a GameSession, got {type(session).__name__}."
            )
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
            return self._lookup(game_id)

    def save(self, session: GameSession, expected_revision: int) -> None:
        if not isinstance(session, GameSession):
            raise TypeError(
                f"'session' must be a GameSession, got {type(session).__name__}."
            )
        with self._lock:
            stored = self._lookup(session.game_id)
            if stored.revision != expected_revision:
                raise StateConflictError(
                    "Game session was modified concurrently.",
                    details=(
                        f"expected revision {expected_revision}, "
                        f"stored revision {stored.revision}",
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
                    "A session cannot change its case.",
                    code="SESSION_CASE_CHANGED",
                )
            old = stored.dialogue_history
            if session.dialogue_history[: len(old)] != old:
                raise ContractValidationError(
                    "Dialogue history is append-only.",
                    code="DIALOGUE_HISTORY_REWRITTEN",
                )
            self._sessions[session.game_id] = session

    def delete(self, game_id: str) -> None:
        with self._lock:
            self._lookup(game_id)
            del self._sessions[game_id]

    def _lookup(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except (KeyError, TypeError):
            raise ResourceNotFoundError(
                f"Unknown game session: {game_id!r}.",
                code="GAME_SESSION_NOT_FOUND",
            ) from None