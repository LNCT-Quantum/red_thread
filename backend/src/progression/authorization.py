from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from shared.contracts.clue import Clue
from shared.contracts.dialogue import DialogueMessage, DialogueRequest, GenerationLimits
from shared.contracts.errors import (
    ContractValidationError,
    PermissionDeniedError,
    ResourceNotFoundError,
    StateConflictError,
)
from shared.contracts.game_state import GameState
from src.case_engine import TESTIMONY_CLUE_TYPE, CaseEngine

from .evidence_reactions import (
    ResolvedReaction,
    reaction_marker,
    validate_evidence_reactions,
)
from .knowledge import NpcKnowledge
from .progression_rules import (
    ProgressionRules,
    current_stage,
    is_stage_reached,
)

__all__ = [
    "FactAuthorization",
    "DialogueAuthorization",
    "PreparedDialogueTurn",
    "AuthorizationService",
]


@dataclass(frozen=True, slots=True)
class FactAuthorization:
    """Facts one suspect may be given, in canonical case order.

    ``concealed_fact_ids`` is the subset of ``authorized_fact_ids`` that the
    NPC data lists as the suspect's secrets.
    """

    suspect_id: str
    stage_id: str
    authorized_fact_ids: tuple[str, ...]
    concealed_fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DialogueAuthorization:
    """Backend-decided inputs for a ``DialogueRequest``."""

    case_id: str
    suspect_id: str
    stage_id: str
    state_revision: int
    authorized_fact_ids: tuple[str, ...]
    presented_clue_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedDialogueTurn:
    """A backend-validated ``DialogueRequest`` plus the evidence reactions that apply.

    ``reactions`` hold only facts that are also in ``request.authorized_fact_ids``.
    """

    request: DialogueRequest
    reactions: tuple[ResolvedReaction, ...]


class AuthorizationService:
    """Decides which clues and facts a given game state may reach.

    Three separate questions are answered, and a fact must pass all of them:

    1. Does it exist in this case? (Case Engine)
    2. Is it unlocked for the player? A stage-gated fact needs its stage; any
       other fact needs a discovered clue that relates to it, or it is a
       baseline fact (no clue relates to it and no suspect lists it as a
       secret).
    3. Is the suspect permitted to know it? (``npc_knowledge.json``: known or
       secret; anything unlisted or marked unknown is refused.)
    """

    __slots__ = ("_engine", "_rules", "_knowledge", "_baseline_fact_ids")

    def __init__(
        self,
        engine: CaseEngine,
        rules: ProgressionRules,
        knowledge: Mapping[str, NpcKnowledge],
    ) -> None:
        if rules.case_id != engine.case_id:
            raise ContractValidationError(
                "Progression rules belong to a different case.",
                details=(f"rules={rules.case_id!r}, engine={engine.case_id!r}",),
                code="PROGRESSION_CASE_MISMATCH",
            )
        rules.validate_against(engine)
        missing = [s for s in engine.case.suspect_ids if s not in knowledge]
        if missing:
            raise ContractValidationError(
                "NPC knowledge is missing for suspects of this case.",
                details=tuple(missing),
                code="NPC_KNOWLEDGE_INVALID",
            )
        validate_evidence_reactions(engine, rules, knowledge)
        self._engine = engine
        self._rules = rules
        self._knowledge: Mapping[str, NpcKnowledge] = knowledge

        clue_linked = {f for clue in engine.list_clues() for f in clue.related_fact_ids}
        secrets = {f for item in knowledge.values() for f in item.secret_fact_ids}
        self._baseline_fact_ids: frozenset[str] = frozenset(
            fact.fact_id
            for fact in engine.list_facts()
            if fact.fact_id not in clue_linked and fact.fact_id not in secrets
        )

    @property
    def engine(self) -> CaseEngine:
        return self._engine

    @property
    def rules(self) -> ProgressionRules:
        return self._rules

    # ------------------------------------------------------------------ state

    def validate_state(self, state: GameState) -> None:
        """Reject a state that belongs to another case or holds foreign IDs."""
        if not isinstance(state, GameState):
            raise TypeError(f"'state' must be a GameState, got {type(state).__name__}.")
        if state.case_id != self._engine.case_id:
            raise ContractValidationError(
                "Game state belongs to a different case.",
                details=(f"state={state.case_id!r}, engine={self._engine.case_id!r}",),
                code="GAME_STATE_CASE_MISMATCH",
            )
        case = self._engine.case
        problems = [
            f"discovered clue {clue_id!r} is not in this case"
            for clue_id in state.discovered_clue_ids
            if not case.has_clue(clue_id)
        ]
        problems += [
            f"interviewed suspect {suspect_id!r} is not in this case"
            for suspect_id in state.interviewed_suspect_ids
            if not case.has_suspect(suspect_id)
        ]
        if state.current_suspect_id is not None and not case.has_suspect(
            state.current_suspect_id
        ):
            problems.append(
                f"current suspect {state.current_suspect_id!r} is not in this case"
            )
        if problems:
            raise ContractValidationError(
                "Game state references records outside this case.",
                details=tuple(problems),
                code="GAME_STATE_FOREIGN_ID",
            )
        current_stage(state, self._rules)  # rejects corrupt stage markers

    # ------------------------------------------------------------------ clues

    def is_clue_unlocked(self, state: GameState, clue_id: str) -> bool:
        """Whether the clue may be found now (stage gate and interview gate)."""
        self.validate_state(state)
        clue = self._get_clue(clue_id)
        return self._clue_unlocked(state, clue)

    def unlocked_clue_ids(self, state: GameState) -> tuple[str, ...]:
        """Unlocked clues, discovered or not, in canonical case order."""
        self.validate_state(state)
        return tuple(
            clue.clue_id
            for clue in self._engine.list_clues()
            if self._clue_unlocked(state, clue)
        )

    def discoverable_clue_ids(self, state: GameState) -> tuple[str, ...]:
        """Unlocked clues that have not been discovered yet."""
        discovered = set(state.discovered_clue_ids)
        return tuple(c for c in self.unlocked_clue_ids(state) if c not in discovered)

    def require_clue_discoverable(self, state: GameState, clue_id: str) -> Clue:
        """Return the clue if it may be discovered now; raise otherwise."""
        self.validate_state(state)
        clue = self._get_clue(clue_id)
        if clue.clue_id in state.discovered_clue_ids:
            raise StateConflictError(
                "Clue has already been discovered.",
                details=(clue.clue_id,),
                code="CLUE_ALREADY_DISCOVERED",
            )
        if not self._clue_unlocked(state, clue):
            raise PermissionDeniedError(
                "Clue is not unlocked yet.",
                details=(clue.clue_id,),
                code="CLUE_LOCKED",
            )
        return clue

    def require_clue_presentable(self, state: GameState, clue_id: str) -> Clue:
        """Return the clue if the detective has discovered it; raise otherwise."""
        self.validate_state(state)
        clue = self._get_clue(clue_id)
        if clue.clue_id not in state.discovered_clue_ids:
            raise PermissionDeniedError(
                "Clue has not been discovered, so it cannot be presented.",
                details=(clue.clue_id,),
                code="CLUE_NOT_DISCOVERED",
            )
        return clue

    # ------------------------------------------------------------------ facts

    def unlocked_fact_ids(self, state: GameState) -> tuple[str, ...]:
        """Facts unlocked for the player, regardless of any suspect."""
        self.validate_state(state)
        return self._unlocked_facts(state)

    def authorize_facts(self, state: GameState, suspect_id: str) -> FactAuthorization:
        """Facts that are unlocked AND permitted to ``suspect_id``."""
        self.validate_state(state)
        self._engine.get_suspect(suspect_id)
        knowledge = self._knowledge[suspect_id]
        permitted = knowledge.permitted_fact_ids
        secrets = set(knowledge.secret_fact_ids)
        authorized = tuple(f for f in self._unlocked_facts(state) if f in permitted)
        return FactAuthorization(
            suspect_id=suspect_id,
            stage_id=current_stage(state, self._rules).stage_id,
            authorized_fact_ids=authorized,
            concealed_fact_ids=tuple(f for f in authorized if f in secrets),
        )

    # --------------------------------------------------------------- dialogue

    def authorize_dialogue(
        self,
        state: GameState,
        suspect_id: str,
        presented_clue_ids: Iterable[str] = (),
    ) -> DialogueAuthorization:
        """Compute, entirely on the backend, what a dialogue turn may use."""
        self.validate_state(state)
        self._require_active(state)
        presented = self._checked_presented_clues(state, presented_clue_ids)
        facts = self.authorize_facts(state, suspect_id)
        return DialogueAuthorization(
            case_id=state.case_id,
            suspect_id=suspect_id,
            stage_id=facts.stage_id,
            state_revision=state.revision,
            authorized_fact_ids=facts.authorized_fact_ids,
            presented_clue_ids=presented,
        )

    def build_dialogue_request(
        self,
        state: GameState,
        *,
        request_id: str,
        suspect_id: str,
        player_message: str,
        presented_clue_ids: Iterable[str] = (),
        dialogue_history: tuple[DialogueMessage, ...] = (),
        generation_limits: GenerationLimits | None = None,
    ) -> DialogueRequest:
        """Build a ``DialogueRequest`` whose fact IDs come only from the backend.

        There is deliberately no parameter for fact IDs: callers cannot supply them.
        """
        decision = self.authorize_dialogue(state, suspect_id, presented_clue_ids)
        limits = generation_limits if generation_limits is not None else GenerationLimits()
        try:
            request = DialogueRequest(
                request_id=request_id,
                case_id=decision.case_id,
                suspect_id=decision.suspect_id,
                player_message=player_message,
                authorized_fact_ids=decision.authorized_fact_ids,
                presented_clue_ids=decision.presented_clue_ids,
                dialogue_history=dialogue_history,
                generation_limits=limits,
            )
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "DialogueRequest could not be built.",
                details=(str(exc),),
                code="DIALOGUE_REQUEST_MALFORMED",
            ) from exc
        self.validate_dialogue_request(state, request)
        return request

    def resolve_evidence_reactions(
        self,
        state: GameState,
        suspect_id: str,
        presented_clue_ids: Iterable[str],
    ) -> tuple[ResolvedReaction, ...]:
        """Reactions of ``suspect_id`` to the clues actually presented to them.

        A clue yields a reaction only if it was discovered, this suspect has a
        reaction for it, and its required stage is reached. Revealed and
        concealed facts are filtered to the suspect's authorized facts, and a
        one-time reaction that was already delivered reveals nothing again.
        """
        self.validate_state(state)
        self._require_active(state)
        presented = self._checked_presented_clues(state, presented_clue_ids)
        facts = self.authorize_facts(state, suspect_id)  # rejects unknown suspects
        authorized = set(facts.authorized_fact_ids)
        by_clue = {
            item.clue_id: item for item in self._knowledge[suspect_id].evidence_reactions
        }
        delivered = set(state.completed_objective_ids)
        resolved: list[ResolvedReaction] = []
        for clue_id in presented:
            reaction = by_clue.get(clue_id)
            if reaction is None:
                continue
            if reaction.required_stage_id is not None and not is_stage_reached(
                state, self._rules, reaction.required_stage_id
            ):
                continue
            is_repeat = (
                not reaction.repeatable
                and reaction_marker(suspect_id, clue_id) in delivered
            )
            resolved.append(
                ResolvedReaction(
                    suspect_id=suspect_id,
                    clue_id=clue_id,
                    reaction_type=reaction.reaction_type,
                    emotional_response=reaction.emotional_response,
                    stated_position=reaction.stated_position,
                    limits=reaction.limits,
                    statement_change=reaction.statement_change,
                    alters_alibi=reaction.alters_alibi,
                    repeatable=reaction.repeatable,
                    is_repeat=is_repeat,
                    reveal_fact_ids=(
                        ()
                        if is_repeat
                        else tuple(f for f in reaction.reveals_fact_ids if f in authorized)
                    ),
                    conceal_fact_ids=tuple(
                        f for f in reaction.conceals_fact_ids if f in authorized
                    ),
                )
            )
        return tuple(resolved)

    def prepare_dialogue_turn(
        self,
        state: GameState,
        *,
        request_id: str,
        suspect_id: str,
        player_message: str,
        presented_clue_ids: Iterable[str] = (),
        dialogue_history: tuple[DialogueMessage, ...] = (),
        generation_limits: GenerationLimits | None = None,
    ) -> PreparedDialogueTurn:
        """Build the request and the evidence reactions for one dialogue turn."""
        presented = tuple(presented_clue_ids)
        request = self.build_dialogue_request(
            state,
            request_id=request_id,
            suspect_id=suspect_id,
            player_message=player_message,
            presented_clue_ids=presented,
            dialogue_history=dialogue_history,
            generation_limits=generation_limits,
        )
        reactions = self.resolve_evidence_reactions(state, suspect_id, presented)
        return PreparedDialogueTurn(request=request, reactions=reactions)

    def validate_dialogue_request(self, state: GameState, request: DialogueRequest) -> None:
        """Verify an existing request against the state; never trust its IDs."""
        if not isinstance(request, DialogueRequest):
            raise TypeError(
                f"'request' must be a DialogueRequest, got {type(request).__name__}."
            )
        self.validate_state(state)
        self._require_active(state)
        if request.case_id != state.case_id:
            raise ContractValidationError(
                "DialogueRequest belongs to a different case than the game state.",
                details=(f"request={request.case_id!r}, state={state.case_id!r}",),
                code="DIALOGUE_CASE_MISMATCH",
            )
        allowed = set(self.authorize_facts(state, request.suspect_id).authorized_fact_ids)
        for fact_id in request.authorized_fact_ids:
            if not self._engine.case.has_fact(fact_id):
                raise ResourceNotFoundError(
                    f"Unknown fact id: {fact_id!r}.",
                    details=(f"case_id={self._engine.case_id}",),
                    code="DIALOGUE_UNKNOWN_FACT",
                )
            if fact_id not in allowed:
                raise PermissionDeniedError(
                    "Request lists a fact that is not authorized for this suspect.",
                    details=(f"{fact_id} for {request.suspect_id}",),
                    code="DIALOGUE_UNAUTHORIZED_FACT",
                )
        self._checked_presented_clues(state, request.presented_clue_ids)

    # -------------------------------------------------------------- internals

    def _get_clue(self, clue_id: str) -> Clue:
        clue = self._engine.get_clue(clue_id)  # ResourceNotFoundError if foreign
        if clue.case_id != self._engine.case_id:
            raise ResourceNotFoundError(
                f"Clue {clue_id!r} does not belong to this case.",
                details=(f"case_id={self._engine.case_id}",),
                code="CLUE_WRONG_CASE",
            )
        return clue

    def _clue_unlocked(self, state: GameState, clue: Clue) -> bool:
        gate = self._rules.clue_gate_stage_id(clue.clue_id)
        if gate is not None and not is_stage_reached(state, self._rules, gate):
            return False
        if (
            clue.clue_type == TESTIMONY_CLUE_TYPE
            and clue.source_entity_id is not None
            and self._engine.case.has_suspect(clue.source_entity_id)
            and clue.source_entity_id not in state.interviewed_suspect_ids
        ):
            return False
        return True

    def _unlocked_facts(self, state: GameState) -> tuple[str, ...]:
        discovered_facts: set[str] = set()
        for clue_id in state.discovered_clue_ids:
            discovered_facts.update(self._engine.get_clue(clue_id).related_fact_ids)
        unlocked: list[str] = []
        for fact in self._engine.list_facts():
            gate = self._rules.fact_gate_stage_id(fact.fact_id)
            if gate is not None:
                ok = is_stage_reached(state, self._rules, gate)
            else:
                ok = (
                    fact.fact_id in discovered_facts
                    or fact.fact_id in self._baseline_fact_ids
                )
            if ok:
                unlocked.append(fact.fact_id)
        return tuple(unlocked)

    def _checked_presented_clues(
        self, state: GameState, clue_ids: Iterable[str]
    ) -> tuple[str, ...]:
        ids = tuple(clue_ids)
        if len(set(ids)) != len(ids):
            raise ContractValidationError(
                "presented_clue_ids contains duplicates.",
                code="PRESENTED_CLUE_DUPLICATE",
            )
        for clue_id in ids:
            self.require_clue_presentable(state, clue_id)
        return ids

    @staticmethod
    def _require_active(state: GameState) -> None:
        if state.status != "active":
            raise StateConflictError(
                "Game is not active.",
                details=(f"status={state.status}",),
                code="GAME_NOT_ACTIVE",
            )