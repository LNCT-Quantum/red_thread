"""NPC dialogue: the sequence documented in ``src/game_state/readme.md`` section 7.

1. validate session / NPC / presented clues and the optional client revision
2. ``GameStateManager.prepare_dialogue_turn``     (facts + reactions decided by the Progression Gate)
3. ``InterrogationService.generate_reply``         (prompt -> LLM -> extract -> check, with fallback)
4. ``GameStateManager.complete_dialogue_turn``      (re-validates the draft and the turn, records reactions)
5. ``GameStateManager.append_dialogue_message`` x2  (player line, then NPC line)

Nothing here builds prompts, picks facts or parses model output: the Progression Gate
decides what the NPC may know and ``src.llm.InterrogationService`` (the documented facade,
``docs/backend_integration_guide.md``) turns that authorized context into a reply.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from shared.contracts.clue import Clue
from shared.contracts.dialogue import DialogueMessage
from shared.contracts.fact import Fact
from shared.contracts.suspect import Suspect
from src.llm import InterrogationResponse, InterrogationService
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


@dataclass(frozen=True, slots=True)
class _NpcContext:
    """Authorized context for one turn, resolved from the case data and the Progression Gate."""

    suspect: Suspect
    facts: tuple[Fact, ...]              # only facts in request.authorized_fact_ids
    clues: tuple[Clue, ...]              # only clues in request.presented_clue_ids
    concealed_fact_ids: tuple[str, ...]  # authorized facts that are this suspect's secrets
    hidden_statements: tuple[str, ...]   # every other fact: must never appear in the reply
    revision: int


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
        # Reuse the gateway's engine: one Ollama client per app. When the engine
        # configuration is invalid there is no service and take_turn answers 503.
        self._llm_service: InterrogationService | None = (
            InterrogationService(engine=llm.engine) if llm.engine is not None else None
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

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
        if not self._llm.configured or self._llm_service is None:
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
            current = runtime.manager.get_game_state(session_id)
            context = self._npc_context(runtime, current, turn)
            collectable_before = set(auth.discoverable_clue_ids(current))
            reached_before = unlocked_stage_ids(current, runtime.gate.manager.rules)

            # -- 3. InterrogationService (bounded by the API timeout) ---------------------
            result = self._generate(turn, context)

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
    @staticmethod
    def _npc_context(runtime: CaseRuntime, state: Any, turn: PreparedDialogueTurn) -> _NpcContext:
        """Everything the facade needs, taken only from the gate-authorized request."""
        engine = runtime.engine
        request = turn.request
        allowed = set(request.authorized_fact_ids)
        fact_auth = runtime.gate.authorization.authorize_facts(state, request.suspect_id)
        return _NpcContext(
            suspect=engine.get_suspect(request.suspect_id),
            facts=tuple(engine.get_fact(f) for f in request.authorized_fact_ids),
            clues=tuple(engine.get_clue(c) for c in request.presented_clue_ids),
            concealed_fact_ids=tuple(f for f in fact_auth.concealed_fact_ids if f in allowed),
            hidden_statements=tuple(
                f.statement for f in engine.list_facts() if f.fact_id not in allowed
            ),
            revision=state.revision,
        )

    def _generate(self, turn: PreparedDialogueTurn, context: _NpcContext) -> InterrogationResponse:
        assert self._llm_service is not None  # checked in take_turn
        future = self._executor.submit(
            self._llm_service.generate_reply,
            turn.request,
            suspect=context.suspect,
            knowledge=context.facts,
            clues=context.clues,
            revision=context.revision,
            reactions=turn.reactions,
            concealed_fact_ids=context.concealed_fact_ids,
            hidden_statements=context.hidden_statements,
        )
        try:
            result = future.result(timeout=self._timeout_s)
        except FutureTimeout:
            future.cancel()
            log.warning("dialogue %s timed out after %.1fs", turn.request.request_id, self._timeout_s)
            # Nothing is committed: no history lines, no reactions, no revision bump.
            raise ApiError(
                503, "LLM_TIMEOUT", "The NPC took too long to answer. Please try again"
            ) from None
        if result.is_fallback:
            log.warning(
                "dialogue %s used fallback after %d attempt(s): %s",
                turn.request.request_id, result.attempts, result.fallback_reason,
            )
        return result

    def _commit(
        self,
        runtime: CaseRuntime,
        session_id: str,
        turn: PreparedDialogueTurn,
        result: InterrogationResponse,
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
