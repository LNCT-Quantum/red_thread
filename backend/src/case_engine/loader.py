

from __future__ import annotations

import json
import re
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import Any, TypeVar

from shared.contracts.case import Case
from shared.contracts.clue import Clue
from shared.contracts.errors import ContractValidationError, ResourceNotFoundError
from shared.contracts.fact import Fact
from shared.contracts.suspect import Suspect

from .timeline import TimelineEvent

__all__ = ["CaseData", "load_case_data", "DEFAULT_DATA_ROOT", "CASE_FILES"]

DEFAULT_DATA_ROOT: Path = Path(__file__).resolve().parents[2] / "case_data"


CASE_FILES: tuple[tuple[str, str], ...] = (
    ("case", "case.json"),
    ("suspects", "suspects.json"),
    ("facts", "facts.json"),
    ("clues", "clues.json"),
    ("timeline", "timeline.json"),
)

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CaseData:
    """Parsed, contract-typed records exactly as found in the files (file order)."""

    case: Case
    suspects: tuple[Suspect, ...]
    facts: tuple[Fact, ...]
    clues: tuple[Clue, ...]
    timeline_events: tuple[TimelineEvent, ...]


def load_case_data(case_id: str, data_root: Path | str | None = None) -> CaseData:
    """Read and parse ``<data_root>/<case_id>/`` into contract types."""
    if not isinstance(case_id, str) or not _CASE_ID_RE.match(case_id):
        raise ContractValidationError(
            f"Invalid case id: {case_id!r}.",
            details=("A case id may contain only letters, digits, '_' and '-'.",),
            code="CASE_ID_INVALID",
        )

    root = Path(data_root) if data_root is not None else DEFAULT_DATA_ROOT
    case_dir = root / case_id
    if not case_dir.is_dir():
        raise ResourceNotFoundError(
            f"Case directory not found for {case_id!r}.",
            details=(str(case_dir),),
            code="CASE_NOT_FOUND",
        )

    missing = tuple(name for _, name in CASE_FILES if not (case_dir / name).is_file())
    if missing:
        raise ResourceNotFoundError(
            f"Required case file(s) missing for {case_id!r}.",
            details=tuple(f"{name} not found in {case_dir}" for name in missing),
            code="CASE_FILE_MISSING",
        )

    raw: dict[str, Any] = {}
    json_errors: list[str] = []
    for key, name in CASE_FILES:
        try:
            text = (case_dir / name).read_text(encoding="utf-8")
            raw[key] = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except (OSError, ValueError) as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
            json_errors.append(f"{name}: {exc}")
    if json_errors:
        raise ContractValidationError(
            f"Case file(s) for {case_id!r} could not be parsed as JSON.",
            details=tuple(json_errors),
            code="CASE_JSON_INVALID",
        )

    problems: list[str] = []
    case = _build(Case, raw["case"], "case.json", problems)
    suspects = _build_many(Suspect, raw["suspects"], "suspects.json", "suspect_id", problems)
    facts = _build_many(Fact, raw["facts"], "facts.json", "fact_id", problems)
    clues = _build_many(Clue, raw["clues"], "clues.json", "clue_id", problems)
    events = _build_many(
        TimelineEvent, raw["timeline"], "timeline.json", "timeline_event_id", problems
    )
    if problems or case is None:
        raise ContractValidationError(
            f"Case records for {case_id!r} do not conform to the shared contracts.",
            details=tuple(problems),
            code="CASE_DATA_MALFORMED",
        )
    return CaseData(case, tuple(suspects), tuple(facts), tuple(clues), tuple(events))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """json.loads hook: a repeated key would silently drop data, so refuse it."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _build(cls: type[T], record: Any, location: str, problems: list[str]) -> T | None:
    """Construct one contract object, recording (not raising) any problem."""
    if not isinstance(record, dict):
        problems.append(f"{location}: expected a JSON object, got {type(record).__name__}.")
        return None

    contract_fields = fields(cls)  # type: ignore[arg-type]
    names = {f.name for f in contract_fields}
    missing = [
        f.name
        for f in contract_fields
        if f.default is MISSING and f.default_factory is MISSING and f.name not in record
    ]
    unknown = [key for key in record if key not in names]
    if missing:
        problems.append(f"{location}: missing required field(s): {', '.join(missing)}.")
    if unknown:
        problems.append(f"{location}: unknown field(s) would be discarded: {', '.join(unknown)}.")
    if missing or unknown:
        return None

    kwargs: dict[str, Any] = {}
    for f in contract_fields:
        if f.name in record:
            value = record[f.name]
            # JSON arrays become tuples; any other type is left for the
            # contract's own validation to reject.
            if isinstance(value, list) and str(f.type).startswith("tuple"):
                value = tuple(value)
            kwargs[f.name] = value
    try:
        return cls(**kwargs)
    except (TypeError, ValueError) as exc:
        problems.append(f"{location}: {exc}")
        return None


def _build_many(
    cls: type[T], records: Any, filename: str, id_field: str, problems: list[str]
) -> list[T]:
    if not isinstance(records, list):
        problems.append(f"{filename}: expected a JSON array, got {type(records).__name__}.")
        return []
    built: list[T] = []
    for index, record in enumerate(records):
        label = f"{filename}[{index}]"
        if isinstance(record, dict) and isinstance(record.get(id_field), str):
            label = f"{label} ({record[id_field]})"
        obj = _build(cls, record, label, problems)
        if obj is not None:
            built.append(obj)
    return built
