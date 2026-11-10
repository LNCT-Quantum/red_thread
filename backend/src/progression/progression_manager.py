from __future__ import annotations

from dataclasses import dataclass, replace

from shared.contracts.errors import PermissionDeniedError, StateConflictError
from shared.contracts.game_state import GameState

from .authorization import AuthorizationService
from .progression_rules import (
    ProgressionRules,
    StageRule,
    current_stage,
    stage_marker,
    unlocked_stage_ids,
    unmet_requirements,
)

__all__ = ["ProgressionResult", "ProgressionManager"]


@dataclass(frozen=True, slots=True)
class ProgressionResult:
    """Outcome of a stage evaluation or unlock request."""

    state: GameState
    previous_stage_id: str
    current_stage_id: str
    newly_unlocked_stage_ids: tuple[str, ...]
    next_stage_id: str | None
    unmet_requirements: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.newly_unlocked_stage_ids)


class ProgressionManager:
    """Stage evaluation and the only code that advances progression state.

    Every method returns a new ``GameState``; inputs are never mutated and the
    revision grows by exactly one when (and only when) the state changes.
    """

    __slots__ = ("_authorization",)

    def __init__(self, authorization: AuthorizationService) -> None:
        self._authorization = authorization

    @property
    def authorization(self) -> AuthorizationService:
        return self._authorization

    @property
    def rules(self) -> ProgressionRules:
        return self._authorization.rules

    def initial_state(self, game_id: str) -> GameState:
        """A fresh game at the initial stage."""
        return GameState(game_id=game_id, case_id=self._authorization.engine.case_id)

    def get_current_stage(self, state: GameState) -> StageRule:
        self._authorization.validate_state(state)
        return current_stage(state, self.rules)

    def evaluate(self, state: GameState) -> ProgressionResult:
        """Unlock every next stage whose conditions are met, one stage at a time.

        Repeating the call on its own output changes nothing.
        """
        self._authorization.validate_state(state)
        self._require_active(state)
        rules = self.rules
        previous = current_stage(state, rules)
        working = state
        unlocked: list[str] = []
        stage = previous
        while True:
            candidate = rules.next_stage(stage.stage_id)
            if candidate is None or unmet_requirements(candidate, working):
                break
            working = replace(
                working,
                completed_objective_ids=working.completed_objective_ids
                + (stage_marker(candidate.stage_id),),
            )
            unlocked.append(candidate.stage_id)
            stage = candidate
        return self._result(state, working, previous, unlocked)

    def unlock_stage(self, state: GameState, stage_id: str) -> ProgressionResult:
        """Explicit unlock request. Never grants anything the rules do not."""
        self._authorization.validate_state(state)
        self._require_active(state)
        rules = self.rules
        index = rules.stage_index(stage_id)
        unlocked = unlocked_stage_ids(state, rules)
        previous = current_stage(state, rules)
        if stage_id in unlocked:
            return self._result(state, state, previous, [])
        if index != len(unlocked):
            raise PermissionDeniedError(
                "Stages cannot be skipped.",
                details=(f"requested {stage_id!r}; next is {rules.stages[len(unlocked)].stage_id!r}",),
                code="STAGE_SKIP_DENIED",
            )
        unmet = unmet_requirements(rules.stages[index], state)
        if unmet:
            raise PermissionDeniedError(
                "Stage requirements are not met.",
                details=unmet,
                code="STAGE_REQUIREMENTS_UNMET",
            )
        working = replace(
            state,
            completed_objective_ids=state.completed_objective_ids + (stage_marker(stage_id),),
        )
        return self._result(state, working, previous, [stage_id])

    def record_interview(self, state: GameState, suspect_id: str) -> GameState:
        """Mark a suspect of this case as interviewed. Repeating is a no-op."""
        self._authorization.validate_state(state)
        self._require_active(state)
        self._authorization.engine.get_suspect(suspect_id)
        if suspect_id in state.interviewed_suspect_ids:
            return state
        return replace(
            state,
            interviewed_suspect_ids=state.interviewed_suspect_ids + (suspect_id,),
            revision=state.revision + 1,
        )

    def discover_clue(self, state: GameState, clue_id: str) -> GameState:
        """Record a clue discovery if the clue is unlocked and not yet found.

        Stage evaluation is a separate step (:meth:`evaluate`).
        """
        self._require_active(state)
        self._authorization.require_clue_discoverable(state, clue_id)
        return replace(
            state,
            discovered_clue_ids=state.discovered_clue_ids + (clue_id,),
            revision=state.revision + 1,
        )

    # -------------------------------------------------------------- internals

    def _result(
        self,
        original: GameState,
        working: GameState,
        previous: StageRule,
        unlocked: list[str],
    ) -> ProgressionResult:
        final = (
            replace(working, revision=original.revision + 1) if unlocked else original
        )
        now = current_stage(final, self.rules)
        following = self.rules.next_stage(now.stage_id)
        return ProgressionResult(
            state=final,
            previous_stage_id=previous.stage_id,
            current_stage_id=now.stage_id,
            newly_unlocked_stage_ids=tuple(unlocked),
            next_stage_id=following.stage_id if following else None,
            unmet_requirements=unmet_requirements(following, final) if following else (),
        )

    @staticmethod
    def _require_active(state: GameState) -> None:
        if state.status != "active":
            raise StateConflictError(
                "Game is not active.",
                details=(f"status={state.status}",),
                code="GAME_NOT_ACTIVE",
            )