# FILE: backend/shared/contracts/dialogue.py
from __future__ import annotations

import json
import math
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime
from typing import Any, Callable, TypeVar

from shared.contracts.errors import ContractValidationError

__all__ = [
    "DialogueMessage",
    "GenerationLimits",
    "DialogueRequest",
    "GenerationMetrics",
    "DialogueDraft",
]

_VALID_SPEAKER_TYPES: frozenset[str] = frozenset({"player", "suspect", "system"})

DEFAULT_MAX_TOKENS: int = 512
DEFAULT_TEMPERATURE: float = 0.7
DEFAULT_TOP_P: float = 1.0
MAX_TEMPERATURE: float = 2.0

T = TypeVar("T")


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


# ---------------------------------------------------------------------------
# Shared validation helpers for the DialogueRequest / DialogueDraft interface
# ---------------------------------------------------------------------------


def _validate_required_string(field_name: str, value: object) -> None:
    """Ensure ``value`` is a non-empty, non-whitespace string."""
    if not isinstance(value, str):
        raise TypeError(
            f"'{field_name}' must be a str, got {type(value).__name__}."
        )
    if not value.strip():
        raise ValueError(f"'{field_name}' must not be empty or whitespace.")


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


def _validate_non_negative_number(field_name: str, value: object) -> None:
    """Ensure ``value`` is a finite, non-negative int or float (not a bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"'{field_name}' must be a number, got {type(value).__name__}."
        )
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"'{field_name}' must be a finite, non-negative number, "
            f"got {value}."
        )


def _validate_non_negative_int(field_name: str, value: object) -> None:
    """Ensure ``value`` is a non-negative integer (not a bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"'{field_name}' must be an int, got {type(value).__name__}."
        )
    if value < 0:
        raise ValueError(
            f"'{field_name}' must be a non-negative integer, got {value}."
        )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value: object) -> datetime:
    """Parse an ISO 8601 string (a trailing ``Z`` means UTC) into a datetime."""
    if not isinstance(value, str):
        raise TypeError(
            "'created_at' must be an ISO 8601 string, "
            f"got {type(value).__name__}."
        )
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"'created_at' must be an ISO 8601 datetime string, got {value!r}."
        ) from exc


def _message_to_dict(message: DialogueMessage) -> dict[str, Any]:
    """Convert a ``DialogueMessage`` into a JSON-safe dictionary."""
    return {
        "message_id": message.message_id,
        "session_id": message.session_id,
        "case_id": message.case_id,
        "speaker_type": message.speaker_type,
        "speaker_id": message.speaker_id,
        "content": message.content,
        "sequence_number": message.sequence_number,
        "created_at": message.created_at.isoformat(),
        "schema_version": message.schema_version,
    }


def _build_record(
    cls: type[T],
    record: object,
    label: str,
    code: str,
    transforms: dict[str, Callable[[Any], Any]] | None = None,
) -> T:
    """Construct a contract from a mapping, raising ``ContractValidationError``.

    Missing required fields and unknown fields are rejected. JSON arrays become
    tuples for tuple-typed fields; any other type mismatch is left for the
    contract's own validation to reject.
    """
    if not isinstance(record, dict):
        raise ContractValidationError(
            f"{label} must be a JSON object.",
            details=(f"Expected a mapping, got {type(record).__name__}.",),
            code=code,
        )

    transforms = transforms or {}
    contract_fields = fields(cls)  # type: ignore[arg-type]
    names = {item.name for item in contract_fields}
    missing = [
        item.name
        for item in contract_fields
        if item.default is MISSING
        and item.default_factory is MISSING
        and item.name not in record
    ]
    unknown = sorted(str(key) for key in record if key not in names)

    problems: list[str] = []
    if missing:
        problems.append(f"missing required field(s): {', '.join(missing)}.")
    if unknown:
        problems.append(f"unknown field(s): {', '.join(unknown)}.")
    if problems:
        raise ContractValidationError(
            f"{label} does not conform to the contract.",
            details=tuple(problems),
            code=code,
        )

    try:
        kwargs: dict[str, Any] = {}
        for item in contract_fields:
            if item.name not in record:
                continue
            value = record[item.name]
            if item.name in transforms:
                value = transforms[item.name](value)
            elif isinstance(value, list) and str(item.type).startswith("tuple"):
                value = tuple(value)
            kwargs[item.name] = value
        return cls(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(
            f"{label} does not conform to the contract.",
            details=(str(exc),),
            code=code,
        ) from exc


def _message_from_dict(record: object, label: str) -> DialogueMessage:
    """Build a ``DialogueMessage`` from a mapping."""
    return _build_record(
        DialogueMessage,
        record,
        label,
        "DIALOGUE_MESSAGE_MALFORMED",
        {"created_at": _parse_datetime},
    )


def _history_from_value(value: object) -> tuple[DialogueMessage, ...]:
    """Build a tuple of ``DialogueMessage`` from a list of mappings."""
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"'dialogue_history' must be a list, got {type(value).__name__}."
        )
    return tuple(
        item
        if isinstance(item, DialogueMessage)
        else _message_from_dict(item, f"dialogue_history[{index}]")
        for index, item in enumerate(value)
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """json.loads hook: a repeated key would silently drop data, so refuse it."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _loads_object(text: object, label: str, code: str) -> dict[str, Any]:
    """Parse ``text`` as a JSON object, raising ``ContractValidationError``."""
    if not isinstance(text, (str, bytes, bytearray)):
        raise ContractValidationError(
            f"{label} JSON must be a str or bytes.",
            details=(f"Got {type(text).__name__}.",),
            code=code,
        )
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ContractValidationError(
            f"{label} could not be parsed as JSON.",
            details=(str(exc),),
            code=code,
        ) from exc
    if not isinstance(parsed, dict):
        raise ContractValidationError(
            f"{label} JSON must be an object.",
            details=(f"Got {type(parsed).__name__}.",),
            code=code,
        )
    return parsed


# ---------------------------------------------------------------------------
# DialogueRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerationLimits:
    """LLM generation parameters carried by a ``DialogueRequest``."""

    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        _validate_required_string("schema_version", self.schema_version)
        self._validate_max_tokens(self.max_tokens)
        self._validate_temperature(self.temperature)
        self._validate_top_p(self.top_p)

    @staticmethod
    def _validate_max_tokens(value: object) -> None:
        """Ensure ``value`` is a positive integer (not a bool)."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"'max_tokens' must be an int, got {type(value).__name__}."
            )
        if value <= 0:
            raise ValueError(
                f"'max_tokens' must be a positive integer, got {value}."
            )

    @staticmethod
    def _validate_temperature(value: object) -> None:
        """Ensure ``value`` is a finite number in the range 0.0 to 2.0."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"'temperature' must be a float, got {type(value).__name__}."
            )
        if not math.isfinite(value) or not 0.0 <= value <= MAX_TEMPERATURE:
            raise ValueError(
                f"'temperature' must be between 0.0 and {MAX_TEMPERATURE} "
                f"inclusive, got {value}."
            )

    @staticmethod
    def _validate_top_p(value: object) -> None:
        """Ensure ``value`` is a finite number greater than 0.0 and at most 1.0."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"'top_p' must be a float, got {type(value).__name__}."
            )
        if not math.isfinite(value) or not 0.0 < value <= 1.0:
            raise ValueError(
                f"'top_p' must be greater than 0.0 and at most 1.0, "
                f"got {value}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: object) -> GenerationLimits:
        """Build ``GenerationLimits`` from a mapping."""
        return _build_record(
            cls, data, "generation_limits", "GENERATION_LIMITS_MALFORMED"
        )


@dataclass(frozen=True, slots=True)
class DialogueRequest:
    """Backend-to-LLM request for one suspect reply.

    ``authorized_fact_ids`` is the only set of facts the LLM may cite, and
    ``presented_clue_ids`` is the only set of clues it may cite.
    """

    request_id: str
    case_id: str
    suspect_id: str
    player_message: str
    authorized_fact_ids: tuple[str, ...]
    presented_clue_ids: tuple[str, ...] = ()
    dialogue_history: tuple[DialogueMessage, ...] = ()
    generation_limits: GenerationLimits = field(default_factory=GenerationLimits)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in (
            "request_id",
            "case_id",
            "suspect_id",
            "player_message",
            "schema_version",
        ):
            _validate_required_string(field_name, getattr(self, field_name))

        _validate_id_collection("authorized_fact_ids", self.authorized_fact_ids)
        _validate_id_collection("presented_clue_ids", self.presented_clue_ids)
        self._validate_dialogue_history(self.case_id, self.dialogue_history)
        self._validate_generation_limits(self.generation_limits)

    @staticmethod
    def _validate_dialogue_history(case_id: str, value: object) -> None:
        """Ensure history is an ordered tuple of messages from one session."""
        if not isinstance(value, tuple):
            raise TypeError(
                f"'dialogue_history' must be a tuple, got {type(value).__name__}."
            )

        seen_message_ids: set[str] = set()
        previous_sequence: int | None = None
        session_id: str | None = None
        for index, message in enumerate(value):
            if not isinstance(message, DialogueMessage):
                raise TypeError(
                    f"'dialogue_history[{index}]' must be a DialogueMessage, "
                    f"got {type(message).__name__}."
                )
            if message.case_id != case_id:
                raise ValueError(
                    f"'dialogue_history[{index}]' belongs to case "
                    f"{message.case_id!r}, expected {case_id!r}."
                )
            if message.message_id in seen_message_ids:
                raise ValueError(
                    "'dialogue_history' contains duplicate message ID: "
                    f"{message.message_id!r}."
                )
            seen_message_ids.add(message.message_id)

            if session_id is None:
                session_id = message.session_id
            elif message.session_id != session_id:
                raise ValueError(
                    f"'dialogue_history[{index}]' belongs to session "
                    f"{message.session_id!r}, expected {session_id!r}."
                )

            if (
                previous_sequence is not None
                and message.sequence_number <= previous_sequence
            ):
                raise ValueError(
                    "'dialogue_history' must be in strictly increasing "
                    f"'sequence_number' order; 'dialogue_history[{index}]' has "
                    f"{message.sequence_number} after {previous_sequence}."
                )
            previous_sequence = message.sequence_number

    @staticmethod
    def _validate_generation_limits(value: object) -> None:
        """Ensure ``value`` is a ``GenerationLimits`` instance."""
        if not isinstance(value, GenerationLimits):
            raise TypeError(
                "'generation_limits' must be a GenerationLimits, "
                f"got {type(value).__name__}."
            )

    def has_authorized_fact(self, fact_id: str) -> bool:
        """Return ``True`` if ``fact_id`` may be cited in the reply."""
        return fact_id in self.authorized_fact_ids

    def has_presented_clue(self, clue_id: str) -> bool:
        """Return ``True`` if ``clue_id`` was presented by the detective."""
        return clue_id in self.presented_clue_ids

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "request_id": self.request_id,
            "case_id": self.case_id,
            "suspect_id": self.suspect_id,
            "player_message": self.player_message,
            "authorized_fact_ids": list(self.authorized_fact_ids),
            "presented_clue_ids": list(self.presented_clue_ids),
            "dialogue_history": [
                _message_to_dict(message) for message in self.dialogue_history
            ],
            "generation_limits": self.generation_limits.to_dict(),
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        """Serialize the request to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: object) -> DialogueRequest:
        """Build a ``DialogueRequest`` from a mapping."""
        return _build_record(
            cls,
            data,
            "DialogueRequest",
            "DIALOGUE_REQUEST_MALFORMED",
            {
                "dialogue_history": _history_from_value,
                "generation_limits": GenerationLimits.from_dict,
            },
        )

    @classmethod
    def from_json(cls, text: str | bytes) -> DialogueRequest:
        """Build a ``DialogueRequest`` from a JSON string."""
        return cls.from_dict(
            _loads_object(text, "DialogueRequest", "DIALOGUE_REQUEST_MALFORMED")
        )


# ---------------------------------------------------------------------------
# DialogueDraft
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    """Generation metrics reported by the LLM Integration Team.

    Times are in milliseconds. ``time_to_first_token_ms`` is measured from the
    start of generation, so it can never exceed ``generation_time_ms``.
    """

    model_id: str
    time_to_first_token_ms: float
    generation_time_ms: float
    prompt_tokens: int
    completion_tokens: int | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in ("model_id", "schema_version"):
            _validate_required_string(field_name, getattr(self, field_name))

        _validate_non_negative_number(
            "time_to_first_token_ms", self.time_to_first_token_ms
        )
        _validate_non_negative_number("generation_time_ms", self.generation_time_ms)
        _validate_non_negative_int("prompt_tokens", self.prompt_tokens)
        if self.completion_tokens is not None:
            _validate_non_negative_int("completion_tokens", self.completion_tokens)

        if self.time_to_first_token_ms > self.generation_time_ms:
            raise ValueError(
                "'time_to_first_token_ms' must not exceed 'generation_time_ms', "
                f"got {self.time_to_first_token_ms} > {self.generation_time_ms}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "model_id": self.model_id,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "generation_time_ms": self.generation_time_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: object) -> GenerationMetrics:
        """Build ``GenerationMetrics`` from a mapping."""
        return _build_record(cls, data, "metrics", "GENERATION_METRICS_MALFORMED")


@dataclass(frozen=True, slots=True)
class DialogueDraft:
    """LLM-generated suspect reply, to be validated by the backend.

    Construction checks the draft in isolation. Use
    :meth:`validate_against_request` to check it against the originating
    ``DialogueRequest``.
    """

    request_id: str
    suspect_id: str
    content: str
    cited_fact_ids: tuple[str, ...]
    cited_clue_ids: tuple[str, ...]
    metrics: GenerationMetrics
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in ("request_id", "suspect_id", "content", "schema_version"):
            _validate_required_string(field_name, getattr(self, field_name))

        _validate_id_collection("cited_fact_ids", self.cited_fact_ids)
        _validate_id_collection("cited_clue_ids", self.cited_clue_ids)
        self._validate_metrics(self.metrics)

    @staticmethod
    def _validate_metrics(value: object) -> None:
        """Ensure ``value`` is a ``GenerationMetrics`` instance."""
        if not isinstance(value, GenerationMetrics):
            raise TypeError(
                "'metrics' must be a GenerationMetrics, "
                f"got {type(value).__name__}."
            )

    def validate_against_request(self, request: DialogueRequest) -> None:
        """Ensure this draft answers ``request`` and cites only allowed IDs.

        Raises:
            TypeError: If ``request`` is not a ``DialogueRequest``.
            ContractValidationError: If the request ID or suspect ID differs,
                a cited fact is not in ``authorized_fact_ids``, or a cited
                clue is not in ``presented_clue_ids``.
        """
        if not isinstance(request, DialogueRequest):
            raise TypeError(
                f"'request' must be a DialogueRequest, got {type(request).__name__}."
            )

        if self.request_id != request.request_id:
            raise ContractValidationError(
                "Draft request_id does not match the originating request.",
                details=(
                    f"expected {request.request_id!r}, got {self.request_id!r}",
                ),
                code="DRAFT_REQUEST_ID_MISMATCH",
            )

        if self.suspect_id != request.suspect_id:
            raise ContractValidationError(
                "Draft suspect_id does not match the originating request.",
                details=(
                    f"expected {request.suspect_id!r}, got {self.suspect_id!r}",
                ),
                code="DRAFT_SUSPECT_MISMATCH",
            )

        unauthorized = tuple(
            fact_id
            for fact_id in self.cited_fact_ids
            if not request.has_authorized_fact(fact_id)
        )
        if unauthorized:
            raise ContractValidationError(
                "Draft cites fact IDs that were not authorized for this request.",
                details=tuple(
                    f"fact {fact_id!r} is not in authorized_fact_ids"
                    for fact_id in unauthorized
                ),
                code="DRAFT_UNAUTHORIZED_FACT",
            )

        unpresented = tuple(
            clue_id
            for clue_id in self.cited_clue_ids
            if not request.has_presented_clue(clue_id)
        )
        if unpresented:
            raise ContractValidationError(
                "Draft cites clue IDs that were not presented in this request.",
                details=tuple(
                    f"clue {clue_id!r} is not in presented_clue_ids"
                    for clue_id in unpresented
                ),
                code="DRAFT_UNPRESENTED_CLUE",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "request_id": self.request_id,
            "suspect_id": self.suspect_id,
            "content": self.content,
            "cited_fact_ids": list(self.cited_fact_ids),
            "cited_clue_ids": list(self.cited_clue_ids),
            "metrics": self.metrics.to_dict(),
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        """Serialize the draft to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: object) -> DialogueDraft:
        """Build a ``DialogueDraft`` from a mapping."""
        return _build_record(
            cls,
            data,
            "DialogueDraft",
            "DIALOGUE_DRAFT_MALFORMED",
            {"metrics": GenerationMetrics.from_dict},
        )

    @classmethod
    def from_json(cls, text: str | bytes) -> DialogueDraft:
        """Build a ``DialogueDraft`` from a JSON string."""
        return cls.from_dict(
            _loads_object(text, "DialogueDraft", "DIALOGUE_DRAFT_MALFORMED")
        )