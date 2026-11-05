

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Case"]


@dataclass(frozen=True, slots=True)
class Case:

    case_id: str
    title: str
    description: str
    victim_id: str
    suspect_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    clue_ids: tuple[str, ...]
    timeline_event_ids: tuple[str, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for name in (
            "case_id",
            "title",
            "description",
            "victim_id",
            "schema_version",
        ):
            self._validate_required_string(name, getattr(self, name))

        for name in (
            "suspect_ids",
            "fact_ids",
            "clue_ids",
            "timeline_event_ids",
        ):
            self._validate_id_collection(name, getattr(self, name))

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
    def _validate_id_collection(field_name: str, value: object) -> None:
        """Ensure ``value`` is a non-empty tuple of unique, non-blank string IDs."""
        if not isinstance(value, tuple):
            raise TypeError(
                f"'{field_name}' must be a tuple, got {type(value).__name__}."
            )
        if not value:
            raise ValueError(f"'{field_name}' must not be empty.")

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

    def has_suspect(self, suspect_id: str) -> bool:
        """Return ``True`` if ``suspect_id`` is a suspect in this case."""
        return suspect_id in self.suspect_ids

    def has_fact(self, fact_id: str) -> bool:
        """Return ``True`` if ``fact_id`` belongs to this case."""
        return fact_id in self.fact_ids

    def has_clue(self, clue_id: str) -> bool:
        """Return ``True`` if ``clue_id`` belongs to this case."""
        return clue_id in self.clue_ids

    def has_timeline_event(self, event_id: str) -> bool:
        """Return ``True`` if ``event_id`` belongs to this case's timeline."""
        return event_id in self.timeline_event_ids