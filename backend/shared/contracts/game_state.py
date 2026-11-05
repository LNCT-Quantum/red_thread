

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GameState"]

_VALID_STATUSES: frozenset[str] = frozenset({"active", "completed", "failed"})


@dataclass(frozen=True, slots=True)
class GameState:
    game_id: str
    case_id: str
    discovered_clue_ids: tuple[str, ...] = ()
    interviewed_suspect_ids: tuple[str, ...] = ()
    completed_objective_ids: tuple[str, ...] = ()
    dialogue_session_ids: tuple[str, ...] = ()
    current_suspect_id: str | None = None
    status: str = "active"
    revision: int = 0
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in ("game_id", "case_id", "schema_version"):
            self._validate_required_string(field_name, getattr(self, field_name))

        for field_name in (
            "discovered_clue_ids",
            "interviewed_suspect_ids",
            "completed_objective_ids",
            "dialogue_session_ids",
        ):
            self._validate_id_collection(field_name, getattr(self, field_name))

        self._validate_current_suspect_id(self.current_suspect_id)
        self._validate_status(self.status)
        self._validate_revision(self.revision)

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

    @staticmethod
    def _validate_current_suspect_id(value: object) -> None:
        """Ensure ``value`` is ``None`` or a non-empty, non-blank string."""
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(
                "'current_suspect_id' must be a str or None, "
                f"got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(
                "'current_suspect_id' must not be empty or whitespace "
                "when provided."
            )

    @staticmethod
    def _validate_status(value: object) -> None:
        """Ensure ``value`` is one of the supported game statuses."""
        if not isinstance(value, str):
            raise TypeError(
                f"'status' must be a str, got {type(value).__name__}."
            )
        if value not in _VALID_STATUSES:
            allowed = ", ".join(repr(item) for item in sorted(_VALID_STATUSES))
            raise ValueError(f"'status' must be one of {allowed}, got {value!r}.")

    @staticmethod
    def _validate_revision(value: object) -> None:
        """Ensure ``value`` is a non-negative integer (not a bool)."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"'revision' must be an int, got {type(value).__name__}."
            )
        if value < 0:
            raise ValueError(
                f"'revision' must be a non-negative integer, got {value}."
            )