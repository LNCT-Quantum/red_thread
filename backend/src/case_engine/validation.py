
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .entities import EntityResolution, classify_entity_id
from .loader import CaseData
from .temporal import (
    OrderingAssumption,
    OrderRelation,
    TemporalDescriptor,
    TemporalFrame,
    derive_ordering,
    parse_timestamp,
)

__all__ = [
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "SUPPORTED_SCHEMA_VERSIONS",
    "validate_case_data",
]

SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    code: str
    location: str
    message: str

    def format(self) -> str:
        return f"[{self.severity.value}] {self.code} @ {self.location}: {self.message}"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.INFO)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def by_code(self, code: str) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.code == code)


def validate_case_data(
    data: CaseData, ordering_assumptions: Iterable[OrderingAssumption] = ()
) -> ValidationReport:
    """Validate ``data`` and return every issue found, in a deterministic order."""
    issues: list[ValidationIssue] = []

    def add(severity: Severity, code: str, location: str, message: str) -> None:
        issues.append(ValidationIssue(severity, code, location, message))

    case = data.case
    assumptions = tuple(ordering_assumptions)

    _check_collections(data, add)
    _check_victim(data, add)
    _check_schema_and_case_ids(data, add)

    suspect_ids = frozenset(case.suspect_ids)
    fact_ids = frozenset(f.fact_id for f in data.facts)
    externals: dict[str, list[str]] = {}

    def check_entity(entity_id: str, record_id: str, location: str) -> None:
        try:
            ref = classify_entity_id(entity_id, suspect_ids, case.victim_id)
        except ValueError as exc:
            add(Severity.ERROR, "INVALID_ENTITY_REFERENCE", location, str(exc))
            return
        if ref.resolution is EntityResolution.UNREGISTERED_EXTERNAL:
            referrers = externals.setdefault(entity_id, [])
            if record_id not in referrers:
                referrers.append(record_id)

    referenced_fact_ids: set[str] = set()

    # Facts
    for fact in data.facts:
        for entity_id in fact.related_entity_ids:
            check_entity(entity_id, fact.fact_id, f"facts.json {fact.fact_id}.related_entity_ids")

    # Clues
    for clue in data.clues:
        location = f"clues.json {clue.clue_id}"
        if not clue.related_fact_ids:
            add(Severity.WARNING, "CLUE_WITHOUT_FACTS", location, "Clue references no facts.")
        for fact_id in clue.related_fact_ids:
            if fact_id in fact_ids:
                referenced_fact_ids.add(fact_id)
            else:
                add(
                    Severity.ERROR,
                    "UNKNOWN_FACT_REFERENCE",
                    f"{location}.related_fact_ids",
                    f"References fact {fact_id!r}, which does not exist.",
                )
        if clue.source_entity_id is not None:
            check_entity(clue.source_entity_id, clue.clue_id, f"{location}.source_entity_id")

    # Timeline
    descriptors: dict[str, TemporalDescriptor] = {}
    for event in data.timeline_events:
        location = f"timeline.json {event.timeline_event_id}"
        for fact_id in event.related_fact_ids:
            if fact_id in fact_ids:
                referenced_fact_ids.add(fact_id)
            else:
                add(
                    Severity.ERROR,
                    "UNKNOWN_FACT_REFERENCE",
                    f"{location}.related_fact_ids",
                    f"References fact {fact_id!r}, which does not exist.",
                )
        for entity_id in event.involved_entity_ids:
            check_entity(entity_id, event.timeline_event_id, f"{location}.involved_entity_ids")
        if not event.involved_entity_ids:
            add(
                Severity.INFO,
                "EVENT_WITHOUT_ENTITIES",
                location,
                "Event lists no involved entities; recorded as-is, not inferred.",
            )
        try:
            descriptor = parse_timestamp(event.timestamp)
        except ValueError as exc:
            add(Severity.ERROR, "TIMESTAMP_INVALID", f"{location}.timestamp", str(exc))
        else:
            descriptors[event.timeline_event_id] = descriptor
            if descriptor.frame is TemporalFrame.UNANCHORED:
                add(
                    Severity.INFO,
                    "TIMESTAMP_UNANCHORED",
                    f"{location}.timestamp",
                    "Timestamp text does not place the event relative to Day 1; "
                    "its order against other events is not established.",
                )

    for entity_id, referrers in externals.items():
        add(
            Severity.INFO,
            "UNREGISTERED_EXTERNAL_ENTITY",
            f"entity {entity_id}",
            "Referenced but has no registered record; treated as an "
            f"external/unresolved reference. Referenced by: {', '.join(referrers)}.",
        )

    for fact in data.facts:
        if fact.fact_id not in referenced_fact_ids:
            add(
                Severity.INFO,
                "FACT_WITHOUT_CLUE_OR_EVENT",
                f"facts.json {fact.fact_id}",
                "Fact is referenced by no clue and no timeline event. It is "
                "kept as canonical; no evidence link is invented.",
            )

    _check_ordering_assumptions(data, descriptors, assumptions, add)
    return ValidationReport(tuple(issues))


def _check_collections(data: CaseData, add) -> None:
    case = data.case
    specs = (
        ("suspect", "suspects.json", "suspect_id", data.suspects, case.suspect_ids),
        ("fact", "facts.json", "fact_id", data.facts, case.fact_ids),
        ("clue", "clues.json", "clue_id", data.clues, case.clue_ids),
        (
            "timeline event",
            "timeline.json",
            "timeline_event_id",
            data.timeline_events,
            case.timeline_event_ids,
        ),
    )
    owners: dict[str, list[str]] = {}
    for kind, filename, attr, records, listed in specs:
        ids = [getattr(r, attr) for r in records]
        if not records:
            add(Severity.ERROR, "EMPTY_COLLECTION", filename, f"No {kind} records were loaded.")

        for record_id, count in Counter(ids).items():
            if count > 1:
                add(
                    Severity.ERROR,
                    "DUPLICATE_ID",
                    filename,
                    f"{kind.capitalize()} ID {record_id!r} appears {count} times.",
                )

        record_set, listed_set = set(ids), set(listed)
        kind_ok = True
        for listed_id in listed:
            if listed_id not in record_set:
                kind_ok = False
                add(
                    Severity.ERROR,
                    "MISSING_RECORD",
                    "case.json",
                    f"Lists {kind} {listed_id!r} but {filename} has no such record.",
                )
        for record_id in dict.fromkeys(ids):
            if record_id not in listed_set:
                kind_ok = False
                add(
                    Severity.ERROR,
                    "RECORD_NOT_LISTED_IN_CASE",
                    filename,
                    f"{kind.capitalize()} {record_id!r} exists but is not listed in "
                    "case.json; it would otherwise be silently discarded.",
                )
        if kind_ok and len(ids) == len(set(ids)) and ids != list(listed):
            add(
                Severity.WARNING,
                "RECORD_ORDER_DIFFERS",
                filename,
                f"Record order differs from case.json; case.json order is used for "
                f"all {kind} queries.",
            )
        for record_id in dict.fromkeys(ids):
            owners.setdefault(record_id, []).append(kind)

    owners.setdefault(case.victim_id, []).append("victim")
    for record_id, kinds in owners.items():
        if len(kinds) > 1:
            add(
                Severity.ERROR,
                "DUPLICATE_ID",
                "case",
                f"ID {record_id!r} is used by more than one record type: {', '.join(kinds)}.",
            )


def _check_victim(data: CaseData, add) -> None:
    case = data.case
    if case.victim_id in case.suspect_ids:
        add(
            Severity.ERROR,
            "VICTIM_LISTED_AS_SUSPECT",
            "case.json",
            f"victim_id {case.victim_id!r} is also listed as a suspect.",
        )
    add(
        Severity.INFO,
        "VICTIM_HAS_NO_RECORD",
        "case.json",
        f"victim_id {case.victim_id!r} is an ID only; no victim record exists in "
        "the case data or the shared contracts.",
    )


def _check_schema_and_case_ids(data: CaseData, add) -> None:
    case = data.case
    versioned = [("case.json", case)]
    versioned += [(f"suspects.json {s.suspect_id}", s) for s in data.suspects]
    versioned += [(f"facts.json {f.fact_id}", f) for f in data.facts]
    versioned += [(f"clues.json {c.clue_id}", c) for c in data.clues]
    versioned += [(f"timeline.json {e.timeline_event_id}", e) for e in data.timeline_events]
    for location, record in versioned:
        if record.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            add(
                Severity.ERROR,
                "UNSUPPORTED_SCHEMA_VERSION",
                location,
                f"schema_version {record.schema_version!r} is not supported "
                f"(supported: {', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))}).",
            )
        if record is not case and hasattr(record, "case_id") and record.case_id != case.case_id:
            add(
                Severity.ERROR,
                "CASE_ID_MISMATCH",
                location,
                f"case_id {record.case_id!r} does not match case.json "
                f"case_id {case.case_id!r}.",
            )


def _check_ordering_assumptions(
    data: CaseData,
    descriptors: dict[str, TemporalDescriptor],
    assumptions: tuple[OrderingAssumption, ...],
    add,
) -> None:
    event_ids = {e.timeline_event_id for e in data.timeline_events}
    edges: dict[str, list[str]] = {}
    for a in assumptions:
        location = f"ordering assumption {a.earlier_event_id} -> {a.later_event_id}"
        unknown = [i for i in (a.earlier_event_id, a.later_event_id) if i not in event_ids]
        if unknown:
            add(
                Severity.ERROR,
                "UNKNOWN_EVENT_REFERENCE",
                location,
                f"References unknown timeline event(s): {', '.join(unknown)}.",
            )
            continue
        if a.earlier_event_id == a.later_event_id:
            add(Severity.ERROR, "ORDERING_ASSUMPTION_SELF_EDGE", location, "An event cannot precede itself.")
            continue
        first = descriptors.get(a.earlier_event_id)
        second = descriptors.get(a.later_event_id)
        if first is not None and second is not None:
            relation, _, _ = derive_ordering(first, second)
            if relation is OrderRelation.AFTER:
                add(
                    Severity.ERROR,
                    "ORDERING_ASSUMPTION_CONFLICT",
                    location,
                    "Contradicts the order already stated by the events' own timestamps.",
                )
                continue
        edges.setdefault(a.earlier_event_id, []).append(a.later_event_id)

    # Cycle detection (iterative three-colour DFS, deterministic node order).
    state: dict[str, int] = {}
    for start in edges:
        if state.get(start):
            continue
        stack = [(start, iter(edges.get(start, ())))]
        state[start] = 1
        while stack:
            node, children = stack[-1]
            for child in children:
                if state.get(child) == 1:
                    add(
                        Severity.ERROR,
                        "ORDERING_ASSUMPTION_CYCLE",
                        "ordering assumptions",
                        f"Assumptions form a cycle through {child!r}.",
                    )
                elif not state.get(child):
                    state[child] = 1
                    stack.append((child, iter(edges.get(child, ()))))
                    break
            else:
                state[node] = 2
                stack.pop()
