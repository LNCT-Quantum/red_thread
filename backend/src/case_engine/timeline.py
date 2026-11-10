

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["TimelineEvent"]


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    timeline_event_id: str
    case_id: str
    timestamp: str
    event_description: str
    involved_entity_ids: tuple[str, ...] = ()
    related_fact_ids: tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in (
            "timeline_event_id",
            "case_id",
            "timestamp",
            "event_description",
            "schema_version",
        ):
            self._validate_required_string(field_name, getattr(self, field_name))

        # An empty ``involved_entity_ids`` is legal: event_010 records that the
        # identities of the people involved are not established.
        self._validate_id_tuple("involved_entity_ids", self.involved_entity_ids)
        self._validate_id_tuple("related_fact_ids", self.related_fact_ids)

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
    def _validate_id_tuple(field_name: str, value: object) -> None:
        """Ensure ``value`` is a tuple of unique, non-blank string IDs."""
        if not isinstance(value, tuple):
            raise TypeError(
                f"'{field_name}' must be a tuple, got {type(value).__name__}."
            )

        seen: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise TypeError(
                    f"'{field_name}[{index}]' must be a str, "
                    f"got {type(item).__name__}."
                )
            if not item.strip():
                raise ValueError(
                    f"'{field_name}[{index}]' must not be empty or whitespace."
                )
            if item in seen:
                raise ValueError(
                    f"'{field_name}' contains duplicate ID: {item!r}."
                )
            seen.add(item)
