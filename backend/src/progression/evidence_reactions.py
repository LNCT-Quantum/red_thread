from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared.contracts.errors import ContractValidationError
from src.case_engine import CaseEngine

if TYPE_CHECKING:
    from .knowledge import NpcKnowledge
    from .progression_rules import ProgressionRules

__all__ = [
    "REACTION_MARKER_PREFIX",
    "REACTION_TYPES",
    "STATEMENT_CHANGES",
    "EvidenceReaction",
    "ResolvedReaction",
    "reaction_marker",
    "validate_evidence_reactions",
]

#: Prefix of the ``GameState.completed_objective_ids`` entry recording that a
#: one-time reaction has been delivered: ``reaction:<suspect_id>:<clue_id>``.
REACTION_MARKER_PREFIX = "reaction:"

REACTION_TYPES: frozenset[str] = frozenset(
    {"acknowledge", "deflect", "conceal", "no_recognition"}
)
STATEMENT_CHANGES: frozenset[str] = frozenset({"none", "acknowledges_discrepancy"})

_REACTION_KEYS: frozenset[str] = frozenset(
    {
        "clue_id",
        "reaction_type",
        "emotional_response",
        "reveals_fact_ids",
        "conceals_fact_ids",
        "stated_position",
        "limits",
        "statement_change",
        "alters_alibi",
        "required_stage_id",
        "repeatable",
    }
)
_REQUIRED_KEYS: tuple[str, ...] = ("clue_id", "reaction_type", "emotional_response")


@dataclass(frozen=True, slots=True)
class EvidenceReaction:
    """How one suspect reacts when confronted with one clue.

    The reaction is stored under the suspect it belongs to, so a clue can only
    ever trigger it for that suspect. ``reveals_fact_ids`` are facts the suspect
    may disclose; ``conceals_fact_ids`` are facts the suspect protects. Both are
    filtered against the backend's fact authorization before use.
    """

    clue_id: str
    reaction_type: str
    emotional_response: str
    reveals_fact_ids: tuple[str, ...] = ()
    conceals_fact_ids: tuple[str, ...] = ()
    stated_position: str = ""
    limits: str = ""
    statement_change: str = "none"
    alters_alibi: bool = False
    required_stage_id: str | None = None
    repeatable: bool = True

    def __post_init__(self) -> None:
        for name in ("clue_id", "reaction_type", "emotional_response"):
            _require_string(name, getattr(self, name))
        for name in ("stated_position", "limits"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(
                    f"'{name}' must be a str, got {type(getattr(self, name)).__name__}."
                )
        if self.reaction_type not in REACTION_TYPES:
            raise ValueError(
                f"'reaction_type' must be one of {sorted(REACTION_TYPES)}, "
                f"got {self.reaction_type!r}."
            )
        if self.statement_change not in STATEMENT_CHANGES:
            raise ValueError(
                f"'statement_change' must be one of {sorted(STATEMENT_CHANGES)}, "
                f"got {self.statement_change!r}."
            )
        for name in ("alters_alibi", "repeatable"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(
                    f"'{name}' must be a bool, got {type(getattr(self, name)).__name__}."
                )
        if self.required_stage_id is not None:
            _require_string("required_stage_id", self.required_stage_id)
        for name in ("reveals_fact_ids", "conceals_fact_ids"):
            _require_id_tuple(name, getattr(self, name))
        overlap = set(self.reveals_fact_ids) & set(self.conceals_fact_ids)
        if overlap:
            raise ValueError(
                f"facts cannot be both revealed and concealed: {sorted(overlap)}."
            )
        if self.reaction_type == "no_recognition" and (
            self.reveals_fact_ids or self.conceals_fact_ids
        ):
            raise ValueError("a 'no_recognition' reaction must not reveal or conceal facts.")

    @classmethod
    def from_dict(cls, data: object, location: str) -> EvidenceReaction:
        if not isinstance(data, dict):
            raise TypeError(f"{location}: expected a JSON object.")
        unknown = sorted(str(k) for k in data if k not in _REACTION_KEYS)
        missing = [k for k in _REQUIRED_KEYS if k not in data]
        if unknown:
            raise ValueError(f"{location}: unknown field(s): {', '.join(unknown)}.")
        if missing:
            raise ValueError(f"{location}: missing field(s): {', '.join(missing)}.")
        kwargs: dict[str, Any] = {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in data.items()
        }
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class ResolvedReaction:
    """A reaction after backend filtering; safe to hand to the dialogue layer.

    ``reveal_fact_ids`` and ``conceal_fact_ids`` contain only facts that are
    authorized for this suspect in the current state. ``is_repeat`` is set when
    a one-time reaction was already delivered: its revelations are then empty.
    """

    suspect_id: str
    clue_id: str
    reaction_type: str
    emotional_response: str
    stated_position: str
    limits: str
    statement_change: str
    alters_alibi: bool
    repeatable: bool
    is_repeat: bool
    reveal_fact_ids: tuple[str, ...]
    conceal_fact_ids: tuple[str, ...]


def reaction_marker(suspect_id: str, clue_id: str) -> str:
    """The ``completed_objective_ids`` entry for a delivered one-time reaction."""
    return f"{REACTION_MARKER_PREFIX}{suspect_id}:{clue_id}"


def validate_evidence_reactions(
    engine: CaseEngine,
    rules: ProgressionRules,
    knowledge: Mapping[str, NpcKnowledge],
) -> None:
    """Check every reaction against the case, the suspect's knowledge and the stages."""
    case = engine.case
    stage_ids = {stage.stage_id for stage in rules.stages}
    problems: list[str] = []
    for suspect_id, entry in knowledge.items():
        permitted = entry.permitted_fact_ids
        seen: set[str] = set()
        for reaction in entry.evidence_reactions:
            where = f"{suspect_id} / {reaction.clue_id}"
            if reaction.clue_id in seen:
                problems.append(f"{where}: more than one reaction for the same clue.")
            seen.add(reaction.clue_id)
            if not case.has_clue(reaction.clue_id):
                problems.append(f"{where}: unknown clue.")
                continue
            related = set(engine.get_clue(reaction.clue_id).related_fact_ids)
            for fact_id in reaction.reveals_fact_ids:
                if fact_id not in permitted:
                    problems.append(
                        f"{where}: reveals fact {fact_id!r} that the suspect does not know."
                    )
                if fact_id not in related:
                    problems.append(
                        f"{where}: reveals fact {fact_id!r} that the clue does not relate to."
                    )
            for fact_id in reaction.conceals_fact_ids:
                if fact_id not in permitted:
                    problems.append(
                        f"{where}: conceals fact {fact_id!r} that the suspect does not know."
                    )
            if reaction.required_stage_id is not None and (
                reaction.required_stage_id not in stage_ids
            ):
                problems.append(
                    f"{where}: unknown stage {reaction.required_stage_id!r}."
                )
    if problems:
        raise ContractValidationError(
            "Evidence reactions do not match the case.",
            details=tuple(problems),
            code="EVIDENCE_REACTIONS_INVALID",
        )


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