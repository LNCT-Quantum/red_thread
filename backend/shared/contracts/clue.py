

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Clue"]


@dataclass(frozen=True, slots=True)
class Clue:
    clue_id: str
    case_id: str
    title: str
    description: str
    clue_type: str
    source: str
    related_fact_ids: tuple[str, ...] = ()
    source_entity_id: str | None = None
    reliability: float = 1.0
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in (
            "clue_id",
            "case_id",
            "title",
            "description",
            "clue_type",
            "source",
            "schema_version",
        ):
            self._validate_required_string(field_name, getattr(self, field_name))

        self._validate_related_fact_ids(self.related_fact_ids)
        self._validate_source_entity_id(self.source_entity_id)
        self._validate_reliability(self.reliability)

    @staticmethod
    def _validate_required_string(field_name: str, value: object) -> None:
        """Ensure ``value`` is a non-empty, non-whitespace string."""
        if not isinstance(value, str):
            raise TypeError(
                f"'{field_name}' must be a str, got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(f"'{field_name}' must not be empty or whitespace.")

    @staticmethod
    def _validate_related_fact_ids(value: object) -> None:
        """Ensure ``value`` is a tuple of unique, non-blank string IDs."""
        if not isinstance(value, tuple):
            raise TypeError(
                "'related_fact_ids' must be a tuple, "
                f"got {type(value).__name__}."
            )

        seen: set[str] = set()
        for index, fact_id in enumerate(value):
            if not isinstance(fact_id, str):
                raise TypeError(
                    f"'related_fact_ids[{index}]' must be a str, "
                    f"got {type(fact_id).__name__}."
                )
            if not fact_id.strip():
                raise ValueError(
                    f"'related_fact_ids[{index}]' must not be empty "
                    "or whitespace."
                )
            if fact_id in seen:
                raise ValueError(
                    f"'related_fact_ids' contains duplicate ID: {fact_id!r}."
                )
            seen.add(fact_id)

    @staticmethod
    def _validate_source_entity_id(value: object) -> None:
        """Ensure ``value`` is ``None`` or a non-empty, non-blank string."""
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(
                "'source_entity_id' must be a str or None, "
                f"got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(
                "'source_entity_id' must not be empty or whitespace "
                "when provided."
            )

    @staticmethod
    def _validate_reliability(value: object) -> None:
        """Ensure ``value`` is a finite number in the range 0.0 to 1.0."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"'reliability' must be a float, got {type(value).__name__}."
            )
        if math.isnan(value) or not 0.0 <= value <= 1.0:
            raise ValueError(
                f"'reliability' must be between 0.0 and 1.0 inclusive, "
                f"got {value}."
            )