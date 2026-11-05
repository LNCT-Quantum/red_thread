

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["DialogueMessage"]

_VALID_SPEAKER_TYPES: frozenset[str] = frozenset({"player", "suspect", "system"})


@dataclass(frozen=True, slots=True)
class DialogueMessage:


    message_id: str
    session_id: str
    case_id: str
    speaker_type: str
    speaker_id: str | None
    content: str
    sequence_number: int
    created_at: datetime
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in (
            "message_id",
            "session_id",
            "case_id",
            "content",
            "schema_version",
        ):
            self._validate_required_string(field_name, getattr(self, field_name))

        self._validate_speaker_type(self.speaker_type)
        self._validate_speaker_id(self.speaker_id)
        self._validate_suspect_has_speaker_id(self.speaker_type, self.speaker_id)
        self._validate_sequence_number(self.sequence_number)
        self._validate_created_at(self.created_at)

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
    def _validate_speaker_type(value: object) -> None:
        """Ensure ``value`` is one of the supported speaker types."""
        if not isinstance(value, str):
            raise TypeError(
                f"'speaker_type' must be a str, got {type(value).__name__}."
            )
        if value not in _VALID_SPEAKER_TYPES:
            allowed = ", ".join(repr(item) for item in sorted(_VALID_SPEAKER_TYPES))
            raise ValueError(
                f"'speaker_type' must be one of {allowed}, got {value!r}."
            )

    @staticmethod
    def _validate_speaker_id(value: object) -> None:
        """Ensure ``value`` is ``None`` or a non-empty, non-blank string."""
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(
                f"'speaker_id' must be a str or None, got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(
                "'speaker_id' must not be empty or whitespace when provided."
            )

    @staticmethod
    def _validate_suspect_has_speaker_id(
        speaker_type: str, speaker_id: str | None
    ) -> None:
        """Ensure suspect messages always identify the speaking suspect."""
        if speaker_type == "suspect" and speaker_id is None:
            raise ValueError(
                "'speaker_id' is required when 'speaker_type' is 'suspect'."
            )

    @staticmethod
    def _validate_sequence_number(value: object) -> None:
        """Ensure ``value`` is a positive integer (not a bool)."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"'sequence_number' must be an int, got {type(value).__name__}."
            )
        if value <= 0:
            raise ValueError(
                f"'sequence_number' must be a positive integer, got {value}."
            )

    @staticmethod
    def _validate_created_at(value: object) -> None:
        """Ensure ``value`` is a ``datetime`` instance."""
        if not isinstance(value, datetime):
            raise TypeError(
                f"'created_at' must be a datetime, got {type(value).__name__}."
            )