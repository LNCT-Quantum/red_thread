"""Incoming request bodies. Unknown fields are rejected so typos never pass silently."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from src.dialogue_generator.prompt_builder import MAX_PLAYER_CHARS

__all__ = [
    "CreateSessionRequest",
    "DialogueTurnRequest",
    "DiscoverClueRequest",
    "CompleteInterviewRequest",
    "MAX_PRESENTED_CLUES",
]

MAX_PRESENTED_CLUES = 10

#: Stable identifiers such as ``case_001`` / ``suspect_001`` / ``clue_001``.
EntityId = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:\-]*$")
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateSessionRequest(_Strict):
    """Start a new investigation. No player data is stored by the backend yet."""

    case_id: EntityId = Field(description="ID of a case returned by GET /cases.")

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"example": {"case_id": "case_001"}},
    )


class DialogueTurnRequest(_Strict):
    npc_id: EntityId = Field(description="Suspect ID from GET /cases/{case_id}/suspects.")
    message: str = Field(
        min_length=1,
        max_length=MAX_PLAYER_CHARS,
        description=f"What the detective says (1-{MAX_PLAYER_CHARS} characters).",
    )
    presented_clue_ids: list[EntityId] = Field(
        default_factory=list,
        max_length=MAX_PRESENTED_CLUES,
        description="Discovered clues the detective shows the suspect during this message.",
    )
    expected_revision: StrictInt | None = Field(
        default=None,
        ge=0,
        description="Optional optimistic-concurrency guard: the session revision the client last saw.",
    )

    @field_validator("presented_clue_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("presented_clue_ids must not contain duplicates")
        return value

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "npc_id": "suspect_002",
                "message": "Where were you on the evening of the murder?",
                "presented_clue_ids": [],
                "expected_revision": 0,
            }
        },
    )


class DiscoverClueRequest(_Strict):
    """Optional body for clue discovery."""

    expected_revision: StrictInt | None = Field(default=None, ge=0)


class CompleteInterviewRequest(_Strict):
    """Optional body for interview completion."""

    expected_revision: StrictInt | None = Field(default=None, ge=0)
