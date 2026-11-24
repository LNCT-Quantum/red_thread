"""Domain objects -> public response models. The single place that decides what is public."""

from __future__ import annotations

from collections.abc import Iterable

from shared.contracts.clue import Clue
from shared.contracts.dialogue import DialogueMessage
from shared.contracts.fact import Fact
from shared.contracts.game_state import GameState
from shared.contracts.suspect import Suspect
from src.case_engine import TimelineEvent
from src.progression.progression_rules import StageRule, unmet_requirements

from .schemas.responses import (
    ClueDetail,
    ClueSummary,
    ConversationSummary,
    FactPublic,
    HistoryMessage,
    NextStageHint,
    SessionState,
    StageInfo,
    SuspectPublic,
    TimelineEventPublic,
)
from .services.runtime import CaseRuntime

__all__ = [
    "CONVERSATION_PREFIX", "conversation_id", "npc_of_conversation", "present_stage",
    "present_state", "present_clue_summary", "present_clue_detail", "present_suspect",
    "present_fact", "present_event", "present_message", "present_next_stage",
    "present_conversations", "present_stages",
]

CONVERSATION_PREFIX = "dlg_"


def conversation_id(npc_id: str) -> str:
    """One conversation per (session, NPC). It is the dialogue-session ID the state manager stores."""
    return f"{CONVERSATION_PREFIX}{npc_id}"


def npc_of_conversation(conv_id: str) -> str:
    return conv_id[len(CONVERSATION_PREFIX):] if conv_id.startswith(CONVERSATION_PREFIX) else conv_id


# ---------------------------------------------------------------------------- stages
def present_stage(runtime: CaseRuntime, stage: StageRule) -> StageInfo:
    rules = runtime.gate.manager.rules
    return StageInfo(
        stage_id=stage.stage_id,
        title=stage.title,
        description=stage.description,
        index=rules.stage_index(stage.stage_id) + 1,
    )


def present_stages(runtime: CaseRuntime, stage_ids: Iterable[str]) -> list[StageInfo]:
    rules = runtime.gate.manager.rules
    return [present_stage(runtime, rules.get_stage(stage_id)) for stage_id in stage_ids]


def present_next_stage(runtime: CaseRuntime, state: GameState) -> NextStageHint | None:
    """Progress toward the next stage, as counts only (never which clues/suspects it needs)."""
    manager = runtime.gate.manager
    nxt = manager.rules.next_stage(manager.get_current_stage(state).stage_id)
    if nxt is None:
        return None
    total = (
        len(nxt.required_clue_ids)
        + len(nxt.required_interviewed_suspect_ids)
        + len(nxt.required_objective_ids)
    )
    unmet = len(unmet_requirements(nxt, state))
    return NextStageHint(requirements_total=total, requirements_met=total - unmet)


def present_state(runtime: CaseRuntime, state: GameState) -> SessionState:
    manager = runtime.gate.manager
    return SessionState(
        session_id=state.game_id,
        case_id=state.case_id,
        status=state.status,  # type: ignore[arg-type]
        revision=state.revision,
        stage=present_stage(runtime, manager.get_current_stage(state)),
        total_stages=len(manager.rules.stages),
        discovered_clue_ids=list(state.discovered_clue_ids),
        interviewed_suspect_ids=list(state.interviewed_suspect_ids),
        current_suspect_id=state.current_suspect_id,
    )


# ----------------------------------------------------------------------- case records
def present_clue_summary(clue: Clue) -> ClueSummary:
    return ClueSummary(
        clue_id=clue.clue_id, title=clue.title, clue_type=clue.clue_type, source=clue.source
    )


def present_clue_detail(clue: Clue) -> ClueDetail:
    return ClueDetail(
        clue_id=clue.clue_id,
        title=clue.title,
        clue_type=clue.clue_type,
        source=clue.source,
        description=clue.description,
    )


def present_suspect(suspect: Suspect) -> SuspectPublic:
    # Deliberately omitted: background, speech_style, personality_traits (LLM prompt inputs).
    return SuspectPublic(
        suspect_id=suspect.suspect_id,
        name=suspect.name,
        age=suspect.age,
        occupation=suspect.occupation,
        public_description=suspect.public_description,
        relationship_to_victim=suspect.relationship_to_victim,
    )


def present_fact(fact: Fact) -> FactPublic:
    # Deliberately omitted: importance and related_entity_ids.
    return FactPublic(fact_id=fact.fact_id, statement=fact.statement, category=fact.category)


def present_event(runtime: CaseRuntime, event: TimelineEvent) -> TimelineEventPublic:
    descriptor = runtime.engine.temporal_descriptor(event.timeline_event_id)
    suspects = set(runtime.engine.case.suspect_ids)
    return TimelineEventPublic(
        event_id=event.timeline_event_id,
        time_text=descriptor.text,
        certainty=descriptor.certainty.value,
        description=event.event_description,
        involved_suspect_ids=[e for e in event.involved_entity_ids if e in suspects],
    )


# ------------------------------------------------------------------------ dialogue
def _turn_number(message: DialogueMessage) -> int:
    # Messages are always stored as (player, suspect) pairs with consecutive sequence numbers.
    return (message.sequence_number + 1) // 2


def present_message(message: DialogueMessage) -> HistoryMessage:
    return HistoryMessage(
        message_id=message.message_id,
        conversation_id=message.session_id,
        npc_id=npc_of_conversation(message.session_id),
        speaker_type=message.speaker_type,  # type: ignore[arg-type]
        speaker_id=message.speaker_id,
        content=message.content,
        sequence_number=message.sequence_number,
        turn_number=_turn_number(message),
        created_at=message.created_at.isoformat(),
    )


def present_conversations(messages: Iterable[DialogueMessage]) -> list[ConversationSummary]:
    counts: dict[str, int] = {}
    for message in messages:
        counts[message.session_id] = counts.get(message.session_id, 0) + 1
    return [
        ConversationSummary(
            conversation_id=conv,
            npc_id=npc_of_conversation(conv),
            message_count=count,
            turn_count=count // 2,
        )
        for conv, count in counts.items()
    ]

