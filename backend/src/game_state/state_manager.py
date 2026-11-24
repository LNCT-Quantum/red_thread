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

# How much past conversation the LLM gets. One turn = player message + suspect reply.
DEFAULT_RECENT_TURNS = 5
MAX_RECENT_TURNS = 10
MESSAGES_PER_TURN = 2


class _Unset:
    """Type of UNSET, so we can tell "not given" apart from None."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True, slots=True)
class StateChange:
    """What a mutation returns. `changed` is False when nothing needed to happen."""

    state: GameState
    changed: bool
    newly_unlocked_stage_ids: tuple[str, ...] = ()


class GameStateManager:
    """Creates game sessions and moves them from one valid state to the next.

    IDs are checked with the Case Engine, and stage/fact rules are left to the
    ProgressionGate. Every change is saved once and bumps the revision by one;
    a no-op or a failure does not touch the revision.
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

    # ---------------------------------------------------------------- sessions

    def create_game_session(
        self, case_id: str | None = None, game_id: str | None = None
    ) -> GameState:
        """Start a new game (for the loaded case unless another case_id is given)."""
        case_id = self._engine.case_id if case_id is None else case_id
        if case_id != self._engine.case_id:
            raise ResourceNotFoundError(f"Unknown case: {case_id!r}.", code="CASE_NOT_FOUND")

        game_id = uuid.uuid4().hex if game_id is None else game_id
        try:
            if self._progression is not None:
                state = self._progression.manager.initial_state(game_id)
            else:
                state = GameState(game_id=game_id, case_id=case_id)
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
        return self._repository.get(game_id).state

    def get_current_stage_id(self, game_id: str) -> str | None:
        """Current stage, or None when there is no Progression Gate."""
        if self._progression is None:
            return None
        state = self.get_game_state(game_id)
        return self._progression.manager.get_current_stage(state).stage_id

    def delete_game_session(self, game_id: str) -> None:
        with self._lock:
            self._repository.delete(game_id)

    # ---------------------------------------------------------------- dialogue

    def get_dialogue_history(self, game_id: str) -> tuple[DialogueMessage, ...]:
        """Every stored message of the game, oldest first."""
        return self._repository.get(game_id).dialogue_history

    def get_recent_dialogue_history(
        self,
        game_id: str,
        dialogue_session_id: str,
        max_turns: int = DEFAULT_RECENT_TURNS,
    ) -> tuple[DialogueMessage, ...]:
        """Last `max_turns` turns of one conversation, used as LLM context."""
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise ContractValidationError("'max_turns' must be an int.", code="RECENT_TURNS_INVALID")
        if not 1 <= max_turns <= MAX_RECENT_TURNS:
            raise ContractValidationError(
                f"'max_turns' must be between 1 and {MAX_RECENT_TURNS}.",
                details=(str(max_turns),),
                code="RECENT_TURNS_INVALID",
            )
        history = self._repository.get(game_id).dialogue_history
        this_chat = tuple(m for m in history if m.session_id == dialogue_session_id)
        return this_chat[-max_turns * MESSAGES_PER_TURN :]

    def append_dialogue_message(
        self,
        game_id: str,
        message: DialogueMessage,
        expected_revision: int | None = None,
    ) -> StateChange:
        """Add a message. Sending the exact same message again is a no-op."""
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

            same_id = next(
                (m for m in session.dialogue_history if m.message_id == message.message_id), None
            )
            if same_id is not None:
                if same_id == message:
                    return StateChange(state, False)
                raise StateConflictError(
                    "A different message with this ID already exists.",
                    details=(message.message_id,),
                    code="DIALOGUE_MESSAGE_ID_CONFLICT",
                )

            last_sequence = max(
                (
                    m.sequence_number
                    for m in session.dialogue_history
                    if m.session_id == message.session_id
                ),
                default=None,
            )
            if last_sequence is not None and message.sequence_number <= last_sequence:
                raise StateConflictError(
                    "Message is out of order for its dialogue session.",
                    details=(f"sequence {message.sequence_number} after {last_sequence}",),
                    code="DIALOGUE_MESSAGE_OUT_OF_ORDER",
                )

            chats = state.dialogue_session_ids
            if message.session_id not in chats:
                chats += (message.session_id,)
            new_state = self._save(
                session,
                replace(state, dialogue_session_ids=chats),
                history=session.dialogue_history + (message,),
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
        """Build the LLM request from stored state (needs a Progression Gate)."""
        gate = self._require_progression("build dialogue requests")
        state, history = self._state_and_recent_history(game_id, dialogue_session_id, max_turns)
        return gate.authorization.build_dialogue_request(
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
        """Like build_dialogue_request, plus evidence reactions. Stores nothing."""
        gate = self._require_progression("prepare dialogue turns")
        state, history = self._state_and_recent_history(game_id, dialogue_session_id, max_turns)
        return gate.authorization.prepare_dialogue_turn(
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
        """Finish a turn once the LLM draft is back and save new one-time reactions.

        Reactions are worked out again from the stored state; if they differ from
        the prepared ones, the turn is stale (or forged) and is rejected.
        """
        gate = self._require_progression("complete dialogue turns")
        if not isinstance(turn, PreparedDialogueTurn):
            raise ContractValidationError(
                "'turn' must be a PreparedDialogueTurn.", code="DIALOGUE_TURN_INVALID"
            )
        if not isinstance(draft, DialogueDraft):
            raise ContractValidationError(
                "'draft' must be a DialogueDraft.", code="DIALOGUE_DRAFT_INVALID"
            )

        authorization = gate.authorization
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)

            draft.validate_against_request(turn.request)
            authorization.validate_dialogue_request(state, turn.request)
            reactions = authorization.resolve_evidence_reactions(
                state, turn.request.suspect_id, turn.request.presented_clue_ids
            )
            if reactions != turn.reactions:
                raise StateConflictError(
                    "Evidence reactions no longer match the game state.",
                    code="DIALOGUE_TURN_STALE",
                )

            # Only one-time reactions that were not already shown get a marker.
            markers = tuple(
                reaction_marker(r.suspect_id, r.clue_id)
                for r in reactions
                if not r.repeatable and not r.is_repeat
            )
            if not markers:
                return StateChange(state, False)

            new_state = self._save(
                session, replace(state, completed_objective_ids=state.completed_objective_ids + markers)
            )
            return StateChange(new_state, True)

    # ----------------------------------------------------------- investigation

    def discover_clue(
        self, game_id: str, clue_id: str, expected_revision: int | None = None
    ) -> StateChange:
        """Record a found clue. Unknown or locked clues fail; a repeat is a no-op."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)

            self._engine.get_clue(clue_id)  # raises for unknown / other-case clue IDs
            if clue_id in state.discovered_clue_ids:
                return StateChange(state, False)
            if self._progression is not None:
                self._progression.authorization.require_clue_discoverable(state, clue_id)

            return self._advance(
                session, replace(state, discovered_clue_ids=state.discovered_clue_ids + (clue_id,))
            )

    def record_interview(
        self, game_id: str, suspect_id: str, expected_revision: int | None = None
    ) -> StateChange:
        """Mark an interview as finished (opening a chat does not count)."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state
            self._require_active(state)

            self._engine.get_suspect(suspect_id)
            if suspect_id in state.interviewed_suspect_ids:
                return StateChange(state, False)

            return self._advance(
                session,
                replace(state, interviewed_suspect_ids=state.interviewed_suspect_ids + (suspect_id,)),
            )

    def update_game_state(
        self,
        game_id: str,
        *,
        current_suspect_id: str | None | _Unset = UNSET,
        status: str | _Unset = UNSET,
        expected_revision: int | None = None,
    ) -> StateChange:
        """Change current_suspect_id / status. Everything else has its own method."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            state = session.state

            changes: dict[str, object] = {}
            if current_suspect_id is not UNSET:
                if current_suspect_id is not None:
                    self._engine.get_suspect(current_suspect_id)
                if current_suspect_id != state.current_suspect_id:
                    changes["current_suspect_id"] = current_suspect_id
            if status is not UNSET and status != state.status:
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
            return StateChange(self._save(session, candidate), True)

    def increment_revision(
        self, game_id: str, expected_revision: int | None = None
    ) -> GameState:
        """Bump the revision by one and nothing else."""
        with self._lock:
            session = self._load(game_id, expected_revision)
            return self._save(session, session.state)

    # ----------------------------------------------------------------- helpers

    def _advance(self, session: GameSession, candidate: GameState) -> StateChange:
        """Let the Progression Gate react (it may unlock stages), then save."""
        unlocked: tuple[str, ...] = ()
        if self._progression is not None:
            result = self._progression.manager.evaluate(candidate)
            candidate = result.state
            unlocked = result.newly_unlocked_stage_ids
        return StateChange(self._save(session, candidate), True, unlocked)

    def _save(
        self,
        session: GameSession,
        new_state: GameState,
        history: tuple[DialogueMessage, ...] | None = None,
    ) -> GameState:
        """Save `new_state` as revision + 1 and return it."""
        new_state = replace(new_state, revision=session.revision + 1)
        if history is None:
            history = session.dialogue_history
        self._repository.save(GameSession(new_state, history), session.revision)
        return new_state

    def _load(self, game_id: str, expected_revision: int | None) -> GameSession:
        session = self._repository.get(game_id)
        if session.state.case_id != self._engine.case_id:
            raise ContractValidationError(
                "Stored session belongs to a different case.", code="GAME_STATE_CASE_MISMATCH"
            )
        if expected_revision is not None and expected_revision != session.revision:
            raise StateConflictError(
                "Game session was modified concurrently.",
                details=(
                    f"expected revision {expected_revision}, stored revision {session.revision}",
                ),
                code="REVISION_CONFLICT",
            )
        return session

    def _state_and_recent_history(
        self, game_id: str, dialogue_session_id: str, max_turns: int
    ) -> tuple[GameState, tuple[DialogueMessage, ...]]:
        state = self.get_game_state(game_id)
        history = self.get_recent_dialogue_history(game_id, dialogue_session_id, max_turns)
        return state, history

    def _require_progression(self, action: str) -> ProgressionGate:
        if self._progression is None:
            raise StateConflictError(
                f"A Progression Gate is required to {action}.", code="PROGRESSION_UNAVAILABLE"
            )
        return self._progression

    @staticmethod
    def _require_active(state: GameState) -> None:
        if state.status != "active":
            raise StateConflictError(
                "Game is not active.", details=(f"status={state.status}",), code="GAME_NOT_ACTIVE"
            )
