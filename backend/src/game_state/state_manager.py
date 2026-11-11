from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace

from shared.contracts.dialogue import DialogueDraft, DialogueMessage, DialogueRequest
from shared.contracts.errors import (
    ContractValidationError,
    ResourceNotFoundError,
    StateConflictError,
)
from shared.contracts.game_state import GameState
from src.case_engine import CaseEngine
from src.progression import PreparedDialogueTurn, ProgressionGate, reaction_marker

from .state_repository import GameSession, GameStateRepository

__all__ = [
    "StateChange",
    "GameStateManager",
    "DEFAULT_RECENT_TURNS",
    "MAX_RECENT_TURNS",
    "MESSAGES_PER_TURN",
    "UNSET",
]

#: Bounded LLM context: a turn is one player message plus one reply.
DEFAULT_RECENT_TURNS = 5
MAX_RECENT_TURNS = 10
MESSAGES_PER_TURN = 2


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


#: Marks a field that ``update_game_state`` must leave untouched.
UNSET = _Unset()


@dataclass(frozen=True, slots=True)
class StateChange:
    """Result of a mutation. ``changed`` is ``False`` for an idempotent no-op."""

    state: GameState
    changed: bool
    newly_unlocked_stage_ids: tuple[str, ...] = ()


class GameStateManager:
    """Session lifecycle and validated state transitions.

    * Case, suspect and clue references are checked with the Case Engine.
    * When a ``ProgressionGate`` is supplied it decides whether a clue may be
      discovered, and it is re-evaluated after clue/interview changes. The
      manager never decides stage conditions or fact authorization itself.
    * Each public mutation is one logical transition: it is computed on
      immutable values, saved once, and raises the revision by exactly one
      (or not at all for a no-op or failure).
    """

    def __init__(
        self,
        engine: CaseEngine,
        repository: GameStateRepository,
        progression: ProgressionGate | None = None,
    ) -> None:
        if progression is not None and progression.authorization.engine is not engine:
            raise ContractValidationError(
                "Progression gate was built on a different Case Engine.",
                code="PROGRESSION_ENGINE_MISMATCH",
            )
        self._engine = engine
        self._repository = repository
        self._progression = progression
        self._lock = threading.RLock()

    # --------------------------------------------------------------- lifecycle

    def create_game_session(
        self, case_id: str | None = None, game_id: str | None = None
    ) -> GameState:
        """Create a fresh session for ``case_id`` (default: the loaded case)."""
        resolved_case = self._engine.case_id if case_id is None else case_id
        if resolved_case != self._engine.case_id:
            raise ResourceNotFoundError(
                f"Unknown case: {resolved_case!r}.",
                code="CASE_NOT_FOUND",
            )
        resolved_id = uuid.uuid4().hex if game_id is None else game_id
        try:
            if self._progression is not None:
                state = self._progression.manager.initial_state(resolved_id)
            else:
                state = GameState(game_id=resolved_id, case_id=resolved_case)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "Game session could not be created.",
                details=(str(exc),),
                code="GAME_SESSION_INVALID",
            ) from exc
        with self._lock:
            self._repository.create(GameSession(state=state))
        return state

    def get_game_state(self, game_id: str) -> GameState:
        """The current state. ``GameState`` is immutable, so it is safe to share."""
        return self._repository.get(game_id).state

    def get_current_stage_id(self, game_id: str) -> str | None:
        """Current investigation stage, or ``None`` without a Progression Gate."""
        if self._progression is None:
            return None
        state = self.get_game_state(game_id)
        return self._progression.manager.get_current_stage(state).stage_id

    def delete_game_session(self, game_id: str) -> None:
        with self._lock:
            self._repository.delete(game_id)

    # -------------------------------------------------------------- dialogue

    def get_dialogue_history(self, game_id: str) -> tuple[DialogueMessage, ...]:
        """The complete stored history of the game, oldest first."""
        return self._repository.get(game_id).dialogue_history

    def get_recent_dialogue_history(
        self,
        game_id: str,
        dialogue_session_id: str,
        max_turns: int = DEFAULT_RECENT_TURNS,
    ) -> tuple[DialogueMessage, ...]:
        """Bounded context for an LLM request: the last ``max_turns`` turns of one
        dialogue session. The stored history is left untouched."""
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise ContractValidationError(
                "'max_turns' must be an int.", code="RECENT_TURNS_INVALID"
            )
        if not 1 <= max_turns <= MAX_RECENT_TURNS:
            raise ContractValidationError(
                f"'max_turns' must be between 1 and {MAX_RECENT_TURNS}.",
                details=(str(max_turns),),
                code="RECENT_TURNS_INVALID",
            )
        history = self._repository.get(game_id).dialogue_history
        in_session = tuple(m for m in history if m.session_id == dialogue_session_id)
        return in_session[-max_turns * MESSAGES_PER_TURN :]

    def append_dialogue_message(
        self,
        game_id: str,
        message: DialogueMessage,
        expected_revision: int | None = None,
    ) -> StateChange:
        """Append one validated message. Re-sending an identical message is a no-op."""
        if not isinstance(message, DialogueMessage):
            raise ContractValidationError(
                "Only DialogueMessage objects may enter the history.",
                details=(type(message).__name__,),
                code="DIALOGUE_MESSAGE_INVALID",
            )
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)
            if message.case_id != state.case_id:
                raise ContractValidationError(
                    "Message belongs to a different case.",
                    details=(f"message={message.case_id!r}, game={state.case_id!r}",),
                    code="DIALOGUE_MESSAGE_CASE_MISMATCH",
                )
            if message.speaker_type == "suspect":
                self._engine.get_suspect(message.speaker_id)  # type: ignore[arg-type]
            for existing in session.dialogue_history:
                if existing.message_id == message.message_id:
                    if existing == message:
                        return StateChange(state, False)
                    raise StateConflictError(
                        "A different message with this ID already exists.",
                        details=(message.message_id,),
                        code="DIALOGUE_MESSAGE_ID_CONFLICT",
                    )
            last = max(
                (
                    m.sequence_number
                    for m in session.dialogue_history
                    if m.session_id == message.session_id
                ),
                default=None,
            )
            if last is not None and message.sequence_number <= last:
                raise StateConflictError(
                    "Message is out of order for its dialogue session.",
                    details=(f"sequence {message.sequence_number} after {last}",),
                    code="DIALOGUE_MESSAGE_OUT_OF_ORDER",
                )
            sessions = state.dialogue_session_ids
            if message.session_id not in sessions:
                sessions = sessions + (message.session_id,)
            new_state = replace(
                state, dialogue_session_ids=sessions, revision=state.revision + 1
            )
            self._commit(
                GameSession(new_state, session.dialogue_history + (message,)),
                state.revision,
            )
            return StateChange(new_state, True)

    def build_dialogue_request(
        self,
        game_id: str,
        *,
        request_id: str,
        suspect_id: str,
        player_message: str,
        dialogue_session_id: str,
        presented_clue_ids: tuple[str, ...] = (),
        max_turns: int = DEFAULT_RECENT_TURNS,
    ) -> DialogueRequest:
        """Build a request from stored state: facts come from the Progression Gate,
        history from the bounded recent window. Requires a Progression Gate."""
        if self._progression is None:
            raise StateConflictError(
                "A Progression Gate is required to build dialogue requests.",
                code="PROGRESSION_UNAVAILABLE",
            )
        state = self.get_game_state(game_id)
        history = self.get_recent_dialogue_history(game_id, dialogue_session_id, max_turns)
        return self._progression.authorization.build_dialogue_request(
            state,
            request_id=request_id,
            suspect_id=suspect_id,
            player_message=player_message,
            presented_clue_ids=presented_clue_ids,
            dialogue_history=history,
        )

    def prepare_dialogue_turn(
        self,
        game_id: str,
        *,
        request_id: str,
        suspect_id: str,
        player_message: str,
        dialogue_session_id: str,
        presented_clue_ids: tuple[str, ...] = (),
        max_turns: int = DEFAULT_RECENT_TURNS,
    ) -> PreparedDialogueTurn:
        """Like :meth:`build_dialogue_request`, plus the evidence reactions that
        apply to the clues presented to this suspect. Nothing is stored."""
        if self._progression is None:
            raise StateConflictError(
                "A Progression Gate is required to prepare dialogue turns.",
                code="PROGRESSION_UNAVAILABLE",
            )
        state = self.get_game_state(game_id)
        history = self.get_recent_dialogue_history(game_id, dialogue_session_id, max_turns)
        return self._progression.authorization.prepare_dialogue_turn(
            state,
            request_id=request_id,
            suspect_id=suspect_id,
            player_message=player_message,
            presented_clue_ids=presented_clue_ids,
            dialogue_history=history,
        )

    def complete_dialogue_turn(
        self,
        game_id: str,
        turn: PreparedDialogueTurn,
        draft: DialogueDraft,
        expected_revision: int | None = None,
    ) -> StateChange:
        """Finish a turn after the LLM draft is received.

        The draft must answer the prepared request and cite only its authorized
        facts and presented clues. The reactions are recomputed from stored state
        and must match the prepared ones, so they cannot be forged or replayed.
        Delivered one-time reactions are recorded in one revision bump; if there
        is nothing to record the call changes nothing.
        """
        if self._progression is None:
            raise StateConflictError(
                "A Progression Gate is required to complete dialogue turns.",
                code="PROGRESSION_UNAVAILABLE",
            )
        if not isinstance(turn, PreparedDialogueTurn):
            raise ContractValidationError(
                "'turn' must be a PreparedDialogueTurn.", code="DIALOGUE_TURN_INVALID"
            )
        if not isinstance(draft, DialogueDraft):
            raise ContractValidationError(
                "'draft' must be a DialogueDraft.", code="DIALOGUE_DRAFT_INVALID"
            )
        authorization = self._progression.authorization
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)
            draft.validate_against_request(turn.request)
            authorization.validate_dialogue_request(state, turn.request)
            expected = authorization.resolve_evidence_reactions(
                state, turn.request.suspect_id, turn.request.presented_clue_ids
            )
            if expected != turn.reactions:
                raise StateConflictError(
                    "Evidence reactions no longer match the game state.",
                    code="DIALOGUE_TURN_STALE",
                )
            markers = tuple(
                reaction_marker(item.suspect_id, item.clue_id)
                for item in expected
                if not item.repeatable and not item.is_repeat
            )
            if not markers:
                return StateChange(state, False)
            new_state = replace(
                state,
                completed_objective_ids=state.completed_objective_ids + markers,
                revision=state.revision + 1,
            )
            self._commit(GameSession(new_state, session.dialogue_history), state.revision)
            return StateChange(new_state, True)

    # ------------------------------------------------------------- investigation

    def discover_clue(
        self, game_id: str, clue_id: str, expected_revision: int | None = None
    ) -> StateChange:
        """Record a clue. Unknown or foreign IDs and locked clues are rejected;
        a clue that is already discovered is a no-op."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)
            self._engine.get_clue(clue_id)  # unknown / other-case IDs raise here
            if clue_id in state.discovered_clue_ids:
                return StateChange(state, False)
            if self._progression is not None:
                self._progression.authorization.require_clue_discoverable(state, clue_id)
            candidate = replace(
                state, discovered_clue_ids=state.discovered_clue_ids + (clue_id,)
            )
            return self._transition(session, candidate)

    def record_interview(
        self, game_id: str, suspect_id: str, expected_revision: int | None = None
    ) -> StateChange:
        """Record a completed interview. Called explicitly; opening a conversation
        does not complete one. Repeating it is a no-op."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)
            self._engine.get_suspect(suspect_id)
            if suspect_id in state.interviewed_suspect_ids:
                return StateChange(state, False)
            candidate = replace(
                state,
                interviewed_suspect_ids=state.interviewed_suspect_ids + (suspect_id,),
            )
            return self._transition(session, candidate)

    # ---------------------------------------------------------------- updates

    def update_game_state(
        self,
        game_id: str,
        *,
        current_suspect_id: str | None | _Unset = UNSET,
        status: str | _Unset = UNSET,
        expected_revision: int | None = None,
    ) -> StateChange:
        """Change the only freely settable fields. Progress collections and stage
        markers can only change through the dedicated operations."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            changes: dict[str, object] = {}
            if not isinstance(current_suspect_id, _Unset):
                if current_suspect_id is not None:
                    self._engine.get_suspect(current_suspect_id)
                if current_suspect_id != state.current_suspect_id:
                    changes["current_suspect_id"] = current_suspect_id
            if not isinstance(status, _Unset) and status != state.status:
                changes["status"] = status
            if not changes:
                return StateChange(state, False)
            self._require_active(state)
            try:
                candidate = replace(state, **changes)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ContractValidationError(
                    "Invalid game state update.",
                    details=(str(exc),),
                    code="GAME_STATE_UPDATE_INVALID",
                ) from exc
            new_state = replace(candidate, revision=state.revision + 1)
            self._commit(GameSession(new_state, session.dialogue_history), state.revision)
            return StateChange(new_state, True)

    def increment_revision(
        self, game_id: str, expected_revision: int | None = None
    ) -> GameState:
        """Explicitly advance the revision by one, as its own logical transition."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            new_state = replace(session.state, revision=session.state.revision + 1)
            self._commit(GameSession(new_state, session.dialogue_history), session.revision)
            return new_state

    # -------------------------------------------------------------- internals

    def _transition(self, session: GameSession, candidate: GameState) -> StateChange:
        """Apply progression evaluation, then save once with a single revision bump."""
        base_revision = session.revision
        unlocked: tuple[str, ...] = ()
        if self._progression is not None:
            result = self._progression.manager.evaluate(candidate)
            candidate = result.state
            unlocked = result.newly_unlocked_stage_ids
        new_state = replace(candidate, revision=base_revision + 1)
        self._commit(GameSession(new_state, session.dialogue_history), base_revision)
        return StateChange(new_state, True, unlocked)

    def _commit(self, session: GameSession, expected_revision: int) -> None:
        self._repository.save(session, expected_revision)

    def _load(self, game_id: str, expected_revision: int | None) -> GameSession:
        session = self._repository.get(game_id)
        if session.state.case_id != self._engine.case_id:
            raise ContractValidationError(
                "Stored session belongs to a different case.",
                code="GAME_STATE_CASE_MISMATCH",
            )
        if expected_revision is not None and expected_revision != session.revision:
            raise StateConflictError(
                "Game session was modified concurrently.",
                details=(
                    f"expected revision {expected_revision}, "
                    f"stored revision {session.revision}",
                ),
                code="REVISION_CONFLICT",
            )
        return session

    @staticmethod
    def _require_active(state: GameState) -> None:
        if state.status != "active":
            raise StateConflictError(
                "Game is not active.",
                details=(f"status={state.status}",),
                code="GAME_NOT_ACTIVE",
            )