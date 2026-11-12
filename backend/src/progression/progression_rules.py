from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.contracts.errors import (
    ContractValidationError,
    StateConflictError,
)
from shared.contracts.game_state import GameState
from src.case_engine import CaseEngine
from src.case_engine.loader import DEFAULT_DATA_ROOT

__all__ = [
    "STAGE_MARKER_PREFIX",
    "RESERVED_OBJECTIVE_PREFIXES",
    "PROGRESSION_FILE",
    "StageRule",
    "ProgressionRules",
    "stage_marker",
    "unlocked_stage_ids",
    "current_stage",
    "is_stage_reached",
    "unmet_requirements",
    "default_rules",
    "load_progression_rules",
]

#: Prefix of the ``GameState.completed_objective_ids`` entry that records an
#: unlocked stage. The initial stage is implicit and is never recorded.
STAGE_MARKER_PREFIX = "stage:"

#: Prefixes of ``completed_objective_ids`` entries written only by the backend
#: (stage unlocks and delivered one-time evidence reactions).
RESERVED_OBJECTIVE_PREFIXES: tuple[str, ...] = (STAGE_MARKER_PREFIX, "reaction:")

_LOGGER = logging.getLogger(__name__)

#: Optional per-case file that overrides the derived default rules.
PROGRESSION_FILE = "progression.json"

_STAGE_KEYS: frozenset[str] = frozenset(
    {
        "stage_id",
        "title",
        "description",
        "required_clue_ids",
        "required_interviewed_suspect_ids",
        "required_objective_ids",
        "unlocks_clue_ids",
        "unlocks_fact_ids",
        "schema_version",
    }
)
_TUPLE_FIELDS: tuple[str, ...] = (
    "required_clue_ids",
    "required_interviewed_suspect_ids",
    "required_objective_ids",
    "unlocks_clue_ids",
    "unlocks_fact_ids",
)


@dataclass(frozen=True, slots=True)
class StageRule:
    """One investigation stage and the conditions for unlocking it.

    ``unlocks_clue_ids`` / ``unlocks_fact_ids`` list the clues and facts that
    are withheld until this stage is reached. Anything not listed by any stage
    is not stage-gated.
    """

    stage_id: str
    title: str
    required_clue_ids: tuple[str, ...] = ()
    required_interviewed_suspect_ids: tuple[str, ...] = ()
    required_objective_ids: tuple[str, ...] = ()
    unlocks_clue_ids: tuple[str, ...] = ()
    unlocks_fact_ids: tuple[str, ...] = ()
    description: str = ""
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("stage_id", "title", "schema_version"):
            _require_string(name, getattr(self, name))
        if not isinstance(self.description, str):
            raise TypeError(
                f"'description' must be a str, got {type(self.description).__name__}."
            )
        for name in _TUPLE_FIELDS:
            _require_id_tuple(name, getattr(self, name))
        if ":" in self.stage_id:
            raise ValueError("'stage_id' must not contain ':'.")
        for objective_id in self.required_objective_ids:
            if objective_id.startswith(RESERVED_OBJECTIVE_PREFIXES):
                raise ValueError(
                    "'required_objective_ids' must not use a reserved "
                    f"prefix {RESERVED_OBJECTIVE_PREFIXES!r}: {objective_id!r}."
                )

    @property
    def has_requirements(self) -> bool:
        return bool(
            self.required_clue_ids
            or self.required_interviewed_suspect_ids
            or self.required_objective_ids
        )


@dataclass(frozen=True, slots=True)
class ProgressionRules:
    """Ordered stages for one case. The first stage is the initial stage."""

    case_id: str
    stages: tuple[StageRule, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _require_string("case_id", self.case_id)
        _require_string("schema_version", self.schema_version)
        if not isinstance(self.stages, tuple) or not self.stages:
            raise ValueError("'stages' must be a non-empty tuple.")
        seen: set[str] = set()
        clue_gates: set[str] = set()
        fact_gates: set[str] = set()
        for index, stage in enumerate(self.stages):
            if not isinstance(stage, StageRule):
                raise TypeError(
                    f"'stages[{index}]' must be a StageRule, "
                    f"got {type(stage).__name__}."
                )
            if stage.stage_id in seen:
                raise ValueError(f"duplicate stage_id: {stage.stage_id!r}.")
            seen.add(stage.stage_id)
            for clue_id in stage.unlocks_clue_ids:
                if clue_id in clue_gates:
                    raise ValueError(f"clue {clue_id!r} is gated by two stages.")
                clue_gates.add(clue_id)
            for fact_id in stage.unlocks_fact_ids:
                if fact_id in fact_gates:
                    raise ValueError(f"fact {fact_id!r} is gated by two stages.")
                fact_gates.add(fact_id)
        if self.stages[0].has_requirements:
            raise ValueError("the initial stage must not have requirements.")

    @property
    def initial_stage(self) -> StageRule:
        return self.stages[0]

    def stage_index(self, stage_id: str) -> int:
        for index, stage in enumerate(self.stages):
            if stage.stage_id == stage_id:
                return index
        raise ContractValidationError(
            f"Unknown stage id: {stage_id!r}.",
            details=(f"case_id={self.case_id}",),
            code="STAGE_UNKNOWN",
        )

    def get_stage(self, stage_id: str) -> StageRule:
        return self.stages[self.stage_index(stage_id)]

    def next_stage(self, stage_id: str) -> StageRule | None:
        index = self.stage_index(stage_id) + 1
        return self.stages[index] if index < len(self.stages) else None

    def clue_gate_stage_id(self, clue_id: str) -> str | None:
        for stage in self.stages:
            if clue_id in stage.unlocks_clue_ids:
                return stage.stage_id
        return None

    def fact_gate_stage_id(self, fact_id: str) -> str | None:
        for stage in self.stages:
            if fact_id in stage.unlocks_fact_ids:
                return stage.stage_id
        return None

    def validate_against(self, engine: CaseEngine) -> None:
        """Check every referenced ID against the loaded case; raise on any problem."""
        case = engine.case
        problems: list[str] = []
        if self.case_id != engine.case_id:
            problems.append(
                f"rules are for case {self.case_id!r}, engine has {engine.case_id!r}."
            )
        for index, stage in enumerate(self.stages):
            where = f"stage {stage.stage_id!r}"
            for clue_id in stage.required_clue_ids + stage.unlocks_clue_ids:
                if not case.has_clue(clue_id):
                    problems.append(f"{where}: unknown clue {clue_id!r}.")
            for suspect_id in stage.required_interviewed_suspect_ids:
                if not case.has_suspect(suspect_id):
                    problems.append(f"{where}: unknown suspect {suspect_id!r}.")
            for fact_id in stage.unlocks_fact_ids:
                if not case.has_fact(fact_id):
                    problems.append(f"{where}: unknown fact {fact_id!r}.")
            for clue_id in stage.required_clue_ids:
                gate = self.clue_gate_stage_id(clue_id)
                if gate is not None and self.stage_index(gate) >= index:
                    problems.append(
                        f"{where}: requires clue {clue_id!r}, which is not "
                        f"available before stage {gate!r} (deadlock)."
                    )
        if problems:
            raise ContractValidationError(
                f"Progression rules do not match case {engine.case_id!r}.",
                details=tuple(problems),
                code="PROGRESSION_RULES_INVALID",
            )


def stage_marker(stage_id: str) -> str:
    """The ``completed_objective_ids`` entry recording that a stage is unlocked."""
    return f"{STAGE_MARKER_PREFIX}{stage_id}"


def unlocked_stage_ids(state: GameState, rules: ProgressionRules) -> tuple[str, ...]:
    """Stages unlocked in ``state``, in order. Rejects corrupt stage markers."""
    markers = {
        item
        for item in state.completed_objective_ids
        if item.startswith(STAGE_MARKER_PREFIX)
    }
    known = {stage_marker(stage.stage_id) for stage in rules.stages}
    foreign = sorted(markers - known)
    if foreign:
        raise StateConflictError(
            "Game state records a stage that the case does not define.",
            details=tuple(foreign),
            code="STAGE_MARKER_UNKNOWN",
        )
    unlocked = [rules.initial_stage.stage_id]
    gap_seen = False
    for stage in rules.stages[1:]:
        present = stage_marker(stage.stage_id) in markers
        if present and gap_seen:
            raise StateConflictError(
                "Game state records a stage unlocked out of order.",
                details=(f"stage {stage.stage_id!r} unlocked after a locked stage",),
                code="STAGE_SKIP_DETECTED",
            )
        if present:
            unlocked.append(stage.stage_id)
        else:
            gap_seen = True
    return tuple(unlocked)


def current_stage(state: GameState, rules: ProgressionRules) -> StageRule:
    """The highest unlocked stage."""
    return rules.get_stage(unlocked_stage_ids(state, rules)[-1])


def is_stage_reached(state: GameState, rules: ProgressionRules, stage_id: str) -> bool:
    rules.stage_index(stage_id)
    return stage_id in unlocked_stage_ids(state, rules)


def unmet_requirements(rule: StageRule, state: GameState) -> tuple[str, ...]:
    """Human-readable list of the rule's conditions that ``state`` does not meet."""
    unmet: list[str] = []
    discovered = set(state.discovered_clue_ids)
    interviewed = set(state.interviewed_suspect_ids)
    completed = set(state.completed_objective_ids)
    for clue_id in rule.required_clue_ids:
        if clue_id not in discovered:
            unmet.append(f"clue not discovered: {clue_id}")
    for suspect_id in rule.required_interviewed_suspect_ids:
        if suspect_id not in interviewed:
            unmet.append(f"suspect not interviewed: {suspect_id}")
    for objective_id in rule.required_objective_ids:
        if objective_id not in completed:
            unmet.append(f"objective not completed: {objective_id}")
    return tuple(unmet)


def default_rules(engine: CaseEngine) -> ProgressionRules:
    """Minimal rules derived only from the case: the initial stage, then a stage
    reached once every suspect in the case has been interviewed. Nothing is
    stage-gated by default."""
    return ProgressionRules(
        case_id=engine.case_id,
        stages=(
            StageRule(stage_id="stage_1", title="Initial investigation"),
            StageRule(
                stage_id="stage_2",
                title="All suspects interviewed",
                required_interviewed_suspect_ids=engine.case.suspect_ids,
            ),
        ),
    )


def load_progression_rules(
    engine: CaseEngine, data_root: Path | str | None = None
) -> ProgressionRules:
    """Load ``progression.json`` if the case ships one, else derive defaults."""
    root = Path(data_root) if data_root is not None else DEFAULT_DATA_ROOT
    path = root / engine.case_id / PROGRESSION_FILE
    if not path.is_file():
        _LOGGER.warning(
            "No %s for case %r; using the generic default progression rules.",
            PROGRESSION_FILE,
            engine.case_id,
        )
        rules = default_rules(engine)
        rules.validate_against(engine)
        return rules
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, ValueError) as exc:
        raise ContractValidationError(
            f"{PROGRESSION_FILE} could not be parsed as JSON.",
            details=(str(exc),),
            code="PROGRESSION_RULES_INVALID",
        ) from exc
    rules = rules_from_dict(raw, engine.case_id)
    rules.validate_against(engine)
    return rules


def rules_from_dict(data: object, case_id: str) -> ProgressionRules:
    """Build rules from ``{"stages": [ {...}, ... ]}``."""
    if not isinstance(data, dict) or set(data) - {"stages", "schema_version"}:
        raise ContractValidationError(
            f"{PROGRESSION_FILE} must be an object with a 'stages' array.",
            code="PROGRESSION_RULES_INVALID",
        )
    stages_raw = data.get("stages")
    if not isinstance(stages_raw, list):
        raise ContractValidationError(
            f"{PROGRESSION_FILE}: 'stages' must be an array.",
            code="PROGRESSION_RULES_INVALID",
        )
    problems: list[str] = []
    stages: list[StageRule] = []
    for index, record in enumerate(stages_raw):
        location = f"stages[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{location}: expected an object.")
            continue
        unknown = sorted(str(k) for k in record if k not in _STAGE_KEYS)
        missing = [k for k in ("stage_id", "title") if k not in record]
        if unknown or missing:
            if unknown:
                problems.append(f"{location}: unknown field(s): {', '.join(unknown)}.")
            if missing:
                problems.append(f"{location}: missing field(s): {', '.join(missing)}.")
            continue
        kwargs: dict[str, Any] = {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in record.items()
        }
        try:
            stages.append(StageRule(**kwargs))
        except (TypeError, ValueError) as exc:
            problems.append(f"{location}: {exc}")
    if problems:
        raise ContractValidationError(
            f"{PROGRESSION_FILE} does not conform to the stage contract.",
            details=tuple(problems),
            code="PROGRESSION_RULES_INVALID",
        )
    try:
        return ProgressionRules(case_id=case_id, stages=tuple(stages))
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(
            f"{PROGRESSION_FILE} does not form valid progression rules.",
            details=(str(exc),),
            code="PROGRESSION_RULES_INVALID",
        ) from exc


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