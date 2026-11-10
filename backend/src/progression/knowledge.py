from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from shared.contracts.errors import ContractValidationError, ResourceNotFoundError
from src.case_engine import CaseEngine
from src.case_engine.loader import DEFAULT_DATA_ROOT

__all__ = ["NpcKnowledge", "NPC_KNOWLEDGE_FILE", "load_npc_knowledge"]

NPC_KNOWLEDGE_FILE = "npc_knowledge.json"

_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "suspect_id",
        "known_fact_ids",
        "unknown_fact_ids",
        "secret_fact_ids",
        "knowledge_notes",
        "schema_version",
    }
)


@dataclass(frozen=True, slots=True)
class NpcKnowledge:
    """What one suspect knows, does not know and conceals (from the case data)."""

    suspect_id: str
    known_fact_ids: tuple[str, ...]
    unknown_fact_ids: tuple[str, ...]
    secret_fact_ids: tuple[str, ...]
    knowledge_notes: str = ""
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("suspect_id", "schema_version"):
            _require_string(name, getattr(self, name))
        if not isinstance(self.knowledge_notes, str):
            raise TypeError(
                "'knowledge_notes' must be a str, "
                f"got {type(self.knowledge_notes).__name__}."
            )
        for name in ("known_fact_ids", "unknown_fact_ids", "secret_fact_ids"):
            _require_id_tuple(name, getattr(self, name))

        known = set(self.known_fact_ids)
        unknown = set(self.unknown_fact_ids)
        secret = set(self.secret_fact_ids)
        overlaps = sorted((known & unknown) | (known & secret) | (unknown & secret))
        if overlaps:
            raise ValueError(
                f"fact IDs appear in more than one knowledge list for "
                f"{self.suspect_id!r}: {', '.join(overlaps)}."
            )

    @property
    def permitted_fact_ids(self) -> frozenset[str]:
        """Facts the suspect may ever speak about: known plus secret."""
        return frozenset(self.known_fact_ids) | frozenset(self.secret_fact_ids)


def load_npc_knowledge(
    engine: CaseEngine, data_root: Path | str | None = None
) -> Mapping[str, NpcKnowledge]:
    """Load ``npc_knowledge.json`` and validate it against the loaded case."""
    root = Path(data_root) if data_root is not None else DEFAULT_DATA_ROOT
    path = root / engine.case_id / NPC_KNOWLEDGE_FILE
    if not path.is_file():
        raise ResourceNotFoundError(
            f"NPC knowledge file not found for {engine.case_id!r}.",
            details=(str(path),),
            code="NPC_KNOWLEDGE_MISSING",
        )
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, ValueError) as exc:
        raise ContractValidationError(
            f"{NPC_KNOWLEDGE_FILE} could not be parsed as JSON.",
            details=(str(exc),),
            code="NPC_KNOWLEDGE_INVALID",
        ) from exc
    if not isinstance(raw, list):
        raise ContractValidationError(
            f"{NPC_KNOWLEDGE_FILE} must contain a JSON array.",
            details=(f"Got {type(raw).__name__}.",),
            code="NPC_KNOWLEDGE_INVALID",
        )

    problems: list[str] = []
    result: dict[str, NpcKnowledge] = {}
    for index, record in enumerate(raw):
        entry = _build_entry(record, index, problems)
        if entry is None:
            continue
        if entry.suspect_id in result:
            problems.append(f"{NPC_KNOWLEDGE_FILE}[{index}]: duplicate suspect_id.")
            continue
        result[entry.suspect_id] = entry

    case = engine.case
    for entry in result.values():
        if not case.has_suspect(entry.suspect_id):
            problems.append(f"unknown suspect_id {entry.suspect_id!r}.")
        for field_name in ("known_fact_ids", "unknown_fact_ids", "secret_fact_ids"):
            for fact_id in getattr(entry, field_name):
                if not case.has_fact(fact_id):
                    problems.append(
                        f"{entry.suspect_id}.{field_name}: unknown fact {fact_id!r}."
                    )
    for suspect_id in case.suspect_ids:
        if suspect_id not in result:
            problems.append(f"no knowledge entry for suspect {suspect_id!r}.")

    if problems:
        raise ContractValidationError(
            f"{NPC_KNOWLEDGE_FILE} does not match case {engine.case_id!r}.",
            details=tuple(problems),
            code="NPC_KNOWLEDGE_INVALID",
        )
    return MappingProxyType(result)


def _build_entry(
    record: Any, index: int, problems: list[str]
) -> NpcKnowledge | None:
    location = f"{NPC_KNOWLEDGE_FILE}[{index}]"
    if not isinstance(record, dict):
        problems.append(f"{location}: expected a JSON object.")
        return None
    unknown_keys = sorted(str(k) for k in record if k not in _ALLOWED_KEYS)
    required = ("suspect_id", "known_fact_ids", "unknown_fact_ids", "secret_fact_ids")
    missing = [k for k in required if k not in record]
    if unknown_keys:
        problems.append(f"{location}: unknown field(s): {', '.join(unknown_keys)}.")
    if missing:
        problems.append(f"{location}: missing field(s): {', '.join(missing)}.")
    if unknown_keys or missing:
        return None
    kwargs: dict[str, Any] = {}
    for key, value in record.items():
        kwargs[key] = tuple(value) if isinstance(value, list) else value
    try:
        return NpcKnowledge(**kwargs)
    except (TypeError, ValueError) as exc:
        problems.append(f"{location}: {exc}")
        return None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _require_string(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"'{field_name}' must be a str, got {type(value).__name__}.")
    if not value.strip():
        raise ValueError(f"'{field_name}' must not be empty or whitespace.")


def _require_id_tuple(field_name: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"'{field_name}' must be a tuple, got {type(value).__name__}.")
    seen: set[str] = set()
    for index, item in enumerate(value):
        _require_string(f"{field_name}[{index}]", item)
        if item in seen:
            raise ValueError(f"'{field_name}' contains duplicate ID: {item!r}.")
        seen.add(item)