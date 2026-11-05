
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Fact"]


@dataclass(frozen=True, slots=True)
class Fact:

    fact_id: str
    case_id: str
    statement: str
    category: str
    importance: str
    related_entity_ids: tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in (
            "fact_id",
            "case_id",
            "statement",
            "category",
            "importance",
            "schema_version",
        ):
            self._validate_required_string(field_name, getattr(self, field_name))

        self._validate_entity_ids(self.related_entity_ids)

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
    def _validate_entity_ids(value: object) -> None:
        """Ensure ``value`` is a tuple of unique, non-blank string IDs."""
        if not isinstance(value, tuple):
            raise TypeError(
                "'related_entity_ids' must be a tuple, "
                f"got {type(value).__name__}."
            )

        seen: set[str] = set()
        for index, entity_id in enumerate(value):
            if not isinstance(entity_id, str):
                raise TypeError(
                    f"'related_entity_ids[{index}]' must be a str, "
                    f"got {type(entity_id).__name__}."
                )
            if not entity_id.strip():
                raise ValueError(
                    f"'related_entity_ids[{index}]' must not be empty "
                    "or whitespace."
                )
            if entity_id in seen:
                raise ValueError(
                    "'related_entity_ids' contains duplicate ID: "
                    f"{entity_id!r}."
                )
            seen.add(entity_id)