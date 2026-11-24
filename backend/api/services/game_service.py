"""Session lifecycle, clues, evidence, interviews and progression views.

Every state change goes through ``GameStateManager``, which in turn defers to the
``ProgressionGate``. This service never edits ``GameState`` itself.
"""

from __future__ import annotations

from ..errors import ApiError
from ..presenters import (
    conversation_id,
    present_clue_detail,
    present_clue_summary,
    present_conversations,
    present_message,
    present_next_stage,
    present_stage,
    present_stages,
    present_state,
)
from ..schemas.responses import (
    ClueCounts,
    ClueDiscoveryData,
    ClueList,
    EvidenceData,
    HistoryData,
    InterviewData,
    ProgressData,
    ProgressionData,
    SessionCreated,
    SessionDeleted,
    UnlocksData,
)
from src.progression.progression_rules import unlocked_stage_ids
from .guards import SessionGuards
from .runtime import CaseRuntime, RuntimeRegistry

__all__ = ["GameService"]


class GameService:
    def __init__(
        self, registry: RuntimeRegistry, guards: SessionGuards, interview_min_turns: int = 1
    ) -> None:
        self._registry = registry
        self._guards = guards
        self._interview_min_turns = interview_min_turns

    # --------------------------------------------------------------------- helpers
    def _session(self, session_id: str):
        return self._registry.find_session(session_id)

    @staticmethod
    def _require_npc(runtime: CaseRuntime, npc_id: str) -> None:
        if not runtime.engine.case.has_suspect(npc_id):
            raise ApiError(404, "NPC_NOT_FOUND", "The requested NPC does not exist")

    @staticmethod
    def _require_clue(runtime: CaseRuntime, clue_id: str) -> None:
        if not runtime.engine.case.has_clue(clue_id):
            raise ApiError(404, "CLUE_NOT_FOUND", "The requested clue does not exist")

    # ------------------------------------------------------------------- lifecycle
    def create_session(self, case_id: str) -> SessionCreated:
        runtime = self._registry.get(case_id)
        state = runtime.manager.create_game_session(case_id=case_id)
        return SessionCreated(session_id=state.game_id, state=present_state(runtime, state))

    def get_session(self, session_id: str):
        runtime, state = self._session(session_id)
        return present_state(runtime, state)

    def delete_session(self, session_id: str) -> SessionDeleted:
        runtime, _ = self._session(session_id)
        with self._guards.commit(session_id):
            runtime.manager.delete_game_session(session_id)
        self._guards.forget(session_id)
        return SessionDeleted(session_id=session_id)

    # --------------------------------------------------------------------- history
    def history(
        self, session_id: str, npc_id: str | None, limit: int, offset: int
    ) -> HistoryData:
        runtime, _ = self._session(session_id)
        if npc_id is not None:
            self._require_npc(runtime, npc_id)
        messages = runtime.manager.get_dialogue_history(session_id)
        if npc_id is not None:
            wanted = conversation_id(npc_id)
            messages = tuple(m for m in messages if m.session_id == wanted)
        page = messages[offset : offset + limit]
        return HistoryData(
            session_id=session_id,
            total=len(messages),
            limit=limit,
            offset=offset,
            messages=[present_message(m) for m in page],
            conversations=present_conversations(messages),
        )

    # ----------------------------------------------------------------------- clues
    def list_discovered_clues(self, session_id: str) -> ClueList:
        runtime, state = self._session(session_id)
        engine = runtime.engine
        return ClueList(
            session_id=session_id,
            revision=state.revision,
            discovered_count=len(state.discovered_clue_ids),
            total_count=len(engine.case.clue_ids),
            clues=[present_clue_detail(engine.get_clue(c)) for c in state.discovered_clue_ids],
        )

    def evidence(self, session_id: str) -> EvidenceData:
        runtime, state = self._session(session_id)
        engine = runtime.engine
        collectable = runtime.gate.authorization.discoverable_clue_ids(state)
        return EvidenceData(
            session_id=session_id,
            revision=state.revision,
            collected=[present_clue_detail(engine.get_clue(c)) for c in state.discovered_clue_ids],
            collectable=[present_clue_summary(engine.get_clue(c)) for c in collectable],
        )

    def discover_clue(
        self, session_id: str, clue_id: str, expected_revision: int | None
    ) -> ClueDiscoveryData:
        runtime, _ = self._session(session_id)
        self._require_clue(runtime, clue_id)
        auth = runtime.gate.authorization
        with self._guards.commit(session_id):
            before = runtime.manager.get_game_state(session_id)
            was_collectable = set(auth.discoverable_clue_ids(before))
            # Authorization (stage gate, interview gate, active game) is enforced here.
            change = runtime.manager.discover_clue(session_id, clue_id, expected_revision)
            after = change.state
            now_collectable = set(auth.discoverable_clue_ids(after))
        newly = [c for c in runtime.engine.case.clue_ids if c in now_collectable - was_collectable]
        return ClueDiscoveryData(
            clue=present_clue_detail(runtime.engine.get_clue(clue_id)),
            already_discovered=not change.changed,
            newly_unlocked_stages=present_stages(runtime, change.newly_unlocked_stage_ids),
            newly_collectable_clues=[
                present_clue_summary(runtime.engine.get_clue(c)) for c in newly
            ],
            state=present_state(runtime, after),
        )

    # ------------------------------------------------------------------ interviews
    def complete_interview(
        self, session_id: str, suspect_id: str, expected_revision: int | None
    ) -> InterviewData:
        """Record a completed interview.

        The existing modules define *how* an interview is recorded but not *when* one counts
        as complete. This API requires that the suspect has actually answered the player at
        least ``interview_min_turns`` times in this session (``API_INTERVIEW_MIN_TURNS``).
        """
        runtime, _ = self._session(session_id)
        self._require_npc(runtime, suspect_id)
        auth = runtime.gate.authorization
        with self._guards.commit(session_id):
            before = runtime.manager.get_game_state(session_id)
            replies = sum(
                1
                for m in runtime.manager.get_dialogue_history(session_id)
                if m.speaker_type == "suspect" and m.speaker_id == suspect_id
            )
            if suspect_id not in before.interviewed_suspect_ids and replies < self._interview_min_turns:
                raise ApiError(
                    409,
                    "INTERVIEW_NOT_READY",
                    "Question this suspect before completing the interview",
                    (f"required_exchanges={self._interview_min_turns}", f"exchanges={replies}"),
                )
            was_collectable = set(auth.discoverable_clue_ids(before))
            change = runtime.manager.record_interview(session_id, suspect_id, expected_revision)
            after = change.state
            now_collectable = set(auth.discoverable_clue_ids(after))
        newly = [c for c in runtime.engine.case.clue_ids if c in now_collectable - was_collectable]
        return InterviewData(
            suspect_id=suspect_id,
            already_completed=not change.changed,
            newly_unlocked_stages=present_stages(runtime, change.newly_unlocked_stage_ids),
            newly_collectable_clues=[
                present_clue_summary(runtime.engine.get_clue(c)) for c in newly
            ],
            state=present_state(runtime, after),
        )

    # ----------------------------------------------------------------- progression
    def progression(self, session_id: str) -> ProgressionData:
        runtime, state = self._session(session_id)
        manager = runtime.gate.manager
        current = manager.get_current_stage(state)
        reached = unlocked_stage_ids(state, manager.rules)
        hint = present_next_stage(runtime, state)
        return ProgressionData(
            session_id=session_id,
            revision=state.revision,
            current_stage=present_stage(runtime, current),
            unlocked_stages=present_stages(runtime, reached),
            total_stages=len(manager.rules.stages),
            is_final_stage=hint is None,
            next_stage=hint,
        )

    def unlocks(self, session_id: str) -> UnlocksData:
        runtime, state = self._session(session_id)
        manager = runtime.gate.manager
        collectable = runtime.gate.authorization.discoverable_clue_ids(state)
        return UnlocksData(
            session_id=session_id,
            revision=state.revision,
            stage_id=manager.get_current_stage(state).stage_id,
            unlocked_stage_ids=list(unlocked_stage_ids(state, manager.rules)),
            collectable_clues=[
                present_clue_summary(runtime.engine.get_clue(c)) for c in collectable
            ],
            discovered_clue_ids=list(state.discovered_clue_ids),
            interviewed_suspect_ids=list(state.interviewed_suspect_ids),
        )

    def progress(self, session_id: str) -> ProgressData:
        runtime, state = self._session(session_id)
        engine = runtime.engine
        manager = runtime.gate.manager
        collectable = runtime.gate.authorization.discoverable_clue_ids(state)
        history = runtime.manager.get_dialogue_history(session_id)
        return ProgressData(
            session_id=session_id,
            case_id=state.case_id,
            status=state.status,  # type: ignore[arg-type]
            revision=state.revision,
            stage=present_stage(runtime, manager.get_current_stage(state)),
            total_stages=len(manager.rules.stages),
            next_stage=present_next_stage(runtime, state),
            clues=ClueCounts(
                discovered=len(state.discovered_clue_ids),
                total=len(engine.case.clue_ids),
                collectable_now=len(collectable),
            ),
            discovered_clues=[
                present_clue_summary(engine.get_clue(c)) for c in state.discovered_clue_ids
            ],
            interviews_completed=list(state.interviewed_suspect_ids),
            interviews_total=len(engine.case.suspect_ids),
            conversations=present_conversations(history),
        )
