"""NPC dialogue: the sequence documented in ``src/game_state/readme.md`` section 7.

1. validate session / NPC / presented clues and the optional client revision
2. ``GameStateManager.prepare_dialogue_turn``     (facts + reactions decided by the Progression Gate)
3. ``DialoguePipeline.generate``                    (prompt -> LLM -> parse -> validate, with fallback)
4. ``GameStateManager.complete_dialogue_turn``      (re-validates the draft and the turn, records reactions)
5. ``GameStateManager.append_dialogue_message`` x2  (player line, then NPC line)

Nothing here builds prompts, picks facts or parses model output.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timezone

from shared.contracts.dialogue import DialogueMessage
from src.dialogue_generator import DialoguePipeline, DialogueResult
from src.progression import PreparedDialogueTurn
from src.progression.progression_rules import unlocked_stage_ids

from ..errors import ApiError
from ..presenters import conversation_id, present_clue_summary, present_stages, present_state
from ..schemas.responses import DialogueData, DialogueTurnInfo
from .guards import SessionGuards
from .llm_gateway import LLMGateway
from .runtime import CaseRuntime, RuntimeRegistry

__all__ = ["DialogueService"]

log = logging.getLogger("redthread.api.dialogue")


class DialogueService:
    def __init__(
        self,
        registry: RuntimeRegistry,
        guards: SessionGuards,
        llm: LLMGateway,
        timeout_s: float,
        concurrency: int = 2,
    ) -> None:
        self._registry = registry
        self._guards = guards
        self._llm = llm
        self._timeout_s = timeout_s
        self._executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="dialogue")
        self._pipelines: dict[str, DialoguePipeline] = {}

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _pipeline(self, runtime: CaseRuntime) -> DialoguePipeline:
        pipeline = self._pipelines.get(runtime.case_id)
        if pipeline is None:
            assert self._llm.adapter is not None
            pipeline = DialoguePipeline(runtime.engine, self._llm.adapter)
            self._pipelines[runtime.case_id] = pipeline
        return pipeline

    # ------------------------------------------------------------------------ public
    def take_turn(
        self,
        *,
        session_id: str,
        npc_id: str,
        message: str,
        presented_clue_ids: list[str],
        expected_revision: int | None,
        request_id: str,
    ) -> DialogueData:
        started = time.perf_counter()
        runtime, state = self._registry.find_session(session_id)

        # -- 1. validation (cheap, and before the model is ever contacted) -------------
        if not runtime.engine.case.has_suspect(npc_id):
            raise ApiError(404, "NPC_NOT_FOUND", "The requested NPC does not exist")
        for clue_id in presented_clue_ids:
            if not runtime.engine.case.has_clue(clue_id):
                raise ApiError(404, "CLUE_NOT_FOUND", "The requested clue does not exist")
        if state.status != "active":
            raise ApiError(409, "GAME_NOT_ACTIVE", "The game session is no longer active")
        if expected_revision is not None and expected_revision != state.revision:
            raise ApiError(
                409,
                "REVISION_CONFLICT",
                "The game state was changed by another request. Reload the session and try again",
                (f"expected revision {expected_revision}, current revision {state.revision}",),
            )
        if not self._llm.configured:
            raise ApiError(503, "LLM_NOT_CONFIGURED", "The dialogue service is not configured")
        if not self._llm.is_available():
            raise ApiError(503, "LLM_UNAVAILABLE", "The dialogue service is temporarily unavailable")

        conv_id = conversation_id(npc_id)
        auth = runtime.gate.authorization
        with self._guards.turn(session_id):
            # -- 2. the Progression Gate decides facts, clues and reactions -------------
            turn = runtime.manager.prepare_dialogue_turn(
                session_id,
                request_id=request_id,
                suspect_id=npc_id,
                player_message=message,
                dialogue_session_id=conv_id,
                presented_clue_ids=tuple(presented_clue_ids),
            )
            collectable_before = set(auth.discoverable_clue_ids(state))
            reached_before = unlocked_stage_ids(state, runtime.gate.manager.rules)

            # -- 3. the existing pipeline (bounded by the API timeout) --------------------
            result = self._generate(runtime, turn)

            # -- 4/5. commit ----------------------------------------------------------------
            with self._guards.commit(session_id):
                final_state, player_msg, npc_msg = self._commit(
                    runtime, session_id, turn, result, npc_id, conv_id, message
                )

        collectable_after = set(auth.discoverable_clue_ids(final_state))
        newly_clues = [
            c for c in runtime.engine.case.clue_ids if c in collectable_after - collectable_before
        ]
        reached_after = unlocked_stage_ids(final_state, runtime.gate.manager.rules)
        newly_stages = [s for s in reached_after if s not in reached_before]
        turn_number = (npc_msg.sequence_number + 1) // 2
        return DialogueData(
            npc_id=npc_id,
            npc_response=npc_msg.content,
            turn=DialogueTurnInfo(
                turn_id=f"{conv_id}:{turn_number}",
                turn_number=turn_number,
                conversation_id=conv_id,
                player_message_id=player_msg.message_id,
                npc_message_id=npc_msg.message_id,
            ),
            is_fallback=result.is_fallback,
            response_time_ms=int((time.perf_counter() - started) * 1000),
            newly_unlocked_stages=present_stages(runtime, newly_stages),
            newly_collectable_clues=[
                present_clue_summary(runtime.engine.get_clue(c)) for c in newly_clues
            ],
            revision=final_state.revision,
            state=present_state(runtime, final_state),
        )

    # --------------------------------------------------------------------- internals
    def _generate(self, runtime: CaseRuntime, turn: PreparedDialogueTurn) -> DialogueResult:
        pipeline = self._pipeline(runtime)
        future = self._executor.submit(pipeline.generate, turn)
        try:
            return future.result(timeout=self._timeout_s)
        except FutureTimeout:
            future.cancel()
            log.warning("dialogue timed out after %.0fs", self._timeout_s)
            raise ApiError(
                503, "LLM_TIMEOUT", "The suspect took too long to answer. Please try again"
            ) from None

    def _commit(
        self,
        runtime: CaseRuntime,
        session_id: str,
        turn: PreparedDialogueTurn,
        result: DialogueResult,
        npc_id: str,
        conv_id: str,
        message: str,
    ):
        manager = runtime.manager
        current = manager.get_game_state(session_id)

        if not result.is_fallback:
            # Re-validates the draft against the request, re-checks authorization and the
            # evidence reactions, and records one-time reactions. A fallback line delivered
            # none of the reactions, so it must not consume them.
            current = manager.complete_dialogue_turn(
                session_id, turn, result.draft, expected_revision=current.revision
            ).state

        history = manager.get_dialogue_history(session_id)
        last = max((m.sequence_number for m in history if m.session_id == conv_id), default=0)
        now = datetime.now(timezone.utc)
        player_msg = DialogueMessage(
            message_id=f"msg_{uuid.uuid4().hex}",
            session_id=conv_id,
            case_id=current.case_id,
            speaker_type="player",
            speaker_id=None,
            content=message,
            sequence_number=last + 1,
            created_at=now,
        )
        npc_msg = DialogueMessage(
            message_id=f"msg_{uuid.uuid4().hex}",
            session_id=conv_id,
            case_id=current.case_id,
            speaker_type="suspect",
            speaker_id=npc_id,
            content=result.draft.content,
            sequence_number=last + 2,
            created_at=datetime.now(timezone.utc),
        )
        change = manager.append_dialogue_message(
            session_id, player_msg, expected_revision=current.revision
        )
        change = manager.append_dialogue_message(
            session_id, npc_msg, expected_revision=change.state.revision
        )
        return change.state, player_msg, npc_msg
