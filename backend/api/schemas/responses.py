"""Outgoing payloads.

These models are an explicit allow-list: only the fields declared here can reach the
frontend. Internal contract fields (``reliability``, ``related_fact_ids``, NPC knowledge,
authorized fact IDs, prompts, LLM metrics, progression markers) are intentionally absent.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

__all__ = [
    "ErrorBody", "ApiEnvelope", "HealthData", "ReadyData", "ComponentStatus",
    "CaseSummary", "CaseDetail", "SuspectPublic", "ClueSummary", "ClueDetail", "FactPublic",
    "TimelineEventPublic", "StageInfo", "SessionState", "SessionCreated", "SessionDeleted",
    "HistoryMessage", "ConversationSummary", "HistoryData", "ClueList", "EvidenceData",
    "ClueDiscoveryData", "InterviewData", "NextStageHint", "ProgressionData", "UnlocksData",
    "ProgressData", "DialogueTurnInfo", "DialogueData", "ClueCounts", "ListData",
]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[str] = Field(default_factory=list)


class ApiEnvelope(BaseModel, Generic[T]):
    request_id: str
    success: bool
    data: T | None = None
    error: ErrorBody | None = None
    schema_version: str = "1.0"


class ListData(BaseModel, Generic[T]):
    items: list[T]
    count: int


# ----------------------------------------------------------------------------- system
class HealthData(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    uptime_seconds: float


class ComponentStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class ReadyData(BaseModel):
    ready: bool
    components: dict[str, ComponentStatus]


# ------------------------------------------------------------------------------- cases
class CaseSummary(BaseModel):
    case_id: str
    title: str
    playable: bool = True


class CaseDetail(CaseSummary):
    description: str
    suspect_count: int


class SuspectPublic(BaseModel):
    suspect_id: str
    name: str
    age: int | None
    occupation: str
    public_description: str
    relationship_to_victim: str


class ClueSummary(BaseModel):
    clue_id: str
    title: str
    clue_type: str
    source: str


class ClueDetail(ClueSummary):
    description: str


class FactPublic(BaseModel):
    fact_id: str
    statement: str
    category: str


class TimelineEventPublic(BaseModel):
    event_id: str
    time_text: str
    certainty: str
    description: str
    involved_suspect_ids: list[str]


# --------------------------------------------------------------------------- sessions
class StageInfo(BaseModel):
    stage_id: str
    title: str
    description: str
    index: int = Field(description="1-based position of the stage.")


class SessionState(BaseModel):
    session_id: str
    case_id: str
    status: Literal["active", "completed", "failed"]
    revision: int
    stage: StageInfo
    total_stages: int
    discovered_clue_ids: list[str]
    interviewed_suspect_ids: list[str]
    current_suspect_id: str | None


class SessionCreated(BaseModel):
    session_id: str
    state: SessionState


class SessionDeleted(BaseModel):
    session_id: str
    deleted: bool = True


class HistoryMessage(BaseModel):
    message_id: str
    conversation_id: str
    npc_id: str = Field(description="The suspect this conversation is with.")
    speaker_type: Literal["player", "suspect", "system"]
    speaker_id: str | None
    content: str
    sequence_number: int
    turn_number: int
    created_at: str


class ConversationSummary(BaseModel):
    conversation_id: str
    npc_id: str
    message_count: int
    turn_count: int


class HistoryData(BaseModel):
    session_id: str
    total: int
    limit: int
    offset: int
    messages: list[HistoryMessage]
    conversations: list[ConversationSummary]


# ------------------------------------------------------------------------------ clues
class ClueCounts(BaseModel):
    discovered: int
    total: int
    collectable_now: int


class ClueList(BaseModel):
    session_id: str
    revision: int
    discovered_count: int
    total_count: int
    clues: list[ClueDetail]


class EvidenceData(BaseModel):
    session_id: str
    revision: int
    collected: list[ClueDetail] = Field(description="Clues the player has discovered.")
    collectable: list[ClueSummary] = Field(
        description="Clues unlocked for this player but not yet discovered."
    )


class ClueDiscoveryData(BaseModel):
    clue: ClueDetail
    already_discovered: bool
    newly_unlocked_stages: list[StageInfo]
    newly_collectable_clues: list[ClueSummary]
    state: SessionState


class InterviewData(BaseModel):
    suspect_id: str
    already_completed: bool
    newly_unlocked_stages: list[StageInfo]
    newly_collectable_clues: list[ClueSummary]
    state: SessionState


# ------------------------------------------------------------------------ progression
class NextStageHint(BaseModel):
    """Progress toward the next stage without naming the clues or suspects it needs."""

    requirements_total: int
    requirements_met: int


class ProgressionData(BaseModel):
    session_id: str
    revision: int
    current_stage: StageInfo
    unlocked_stages: list[StageInfo]
    total_stages: int
    is_final_stage: bool
    next_stage: NextStageHint | None


class UnlocksData(BaseModel):
    session_id: str
    revision: int
    stage_id: str
    unlocked_stage_ids: list[str]
    collectable_clues: list[ClueSummary]
    discovered_clue_ids: list[str]
    interviewed_suspect_ids: list[str]


class ProgressData(BaseModel):
    session_id: str
    case_id: str
    status: Literal["active", "completed", "failed"]
    revision: int
    stage: StageInfo
    total_stages: int
    next_stage: NextStageHint | None
    clues: ClueCounts
    discovered_clues: list[ClueSummary]
    interviews_completed: list[str]
    interviews_total: int
    conversations: list[ConversationSummary]


# ------------------------------------------------------------------------- dialogue
class DialogueTurnInfo(BaseModel):
    turn_id: str
    turn_number: int
    conversation_id: str
    player_message_id: str
    npc_message_id: str


class DialogueData(BaseModel):
    npc_id: str
    npc_response: str
    turn: DialogueTurnInfo
    is_fallback: bool = Field(
        description="True when the model could not produce a valid in-character answer and "
        "the backend's safe deflection line was used instead."
    )
    response_time_ms: int
    newly_unlocked_stages: list[StageInfo]
    newly_collectable_clues: list[ClueSummary]
    revision: int
    state: SessionState
