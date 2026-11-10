

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from shared.contracts.case import Case
from shared.contracts.clue import Clue
from shared.contracts.errors import (
    ContractValidationError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from shared.contracts.fact import Fact
from shared.contracts.suspect import Suspect

from .entities import EntityReference, EntityResolution, classify_entity_id
from .loader import CaseData, load_case_data
from .temporal import (
    OrderBasis,
    OrderingAssumption,
    OrderRelation,
    TemporalCertainty,
    TemporalDescriptor,
    TemporalOrdering,
    derive_ordering,
    parse_timestamp,
)
from .timeline import TimelineEvent
from .validation import ValidationReport, validate_case_data

__all__ = ["CaseEngine", "CaseRegistry", "TESTIMONY_CLUE_TYPE"]

#: ``Clue.clue_type`` value that marks a clue as someone's statement.
TESTIMONY_CLUE_TYPE = "witness_statement"


@dataclass(frozen=True, slots=True)
class CaseRegistry:
    """Complete immutable snapshot of the case, in canonical order."""

    case: Case
    suspects: tuple[Suspect, ...]
    facts: tuple[Fact, ...]
    clues: tuple[Clue, ...]
    timeline_events: tuple[TimelineEvent, ...]
    entity_references: tuple[EntityReference, ...]


@dataclass(frozen=True, slots=True, eq=False)
class _State:
    registry: CaseRegistry
    report: ValidationReport
    assumptions: tuple[OrderingAssumption, ...]
    suspects: Mapping[str, Suspect]
    facts: Mapping[str, Fact]
    clues: Mapping[str, Clue]
    events: Mapping[str, TimelineEvent]
    entities: Mapping[str, EntityReference]
    descriptors: Mapping[str, TemporalDescriptor]
    clues_by_fact: Mapping[str, tuple[Clue, ...]]
    facts_by_clue: Mapping[str, tuple[Fact, ...]]
    events_by_fact: Mapping[str, tuple[TimelineEvent, ...]]
    facts_by_event: Mapping[str, tuple[Fact, ...]]
    facts_by_entity: Mapping[str, tuple[Fact, ...]]
    events_by_entity: Mapping[str, tuple[TimelineEvent, ...]]
    clues_by_source: Mapping[str, tuple[Clue, ...]]
    assumption_edges: Mapping[str, tuple[tuple[str, OrderingAssumption], ...]]


class CaseEngine:
    """Use :meth:`load` (or :meth:`from_case_data`) to obtain an instance."""

    __slots__ = ("_s",)

    def __init__(self, state: _State) -> None:
        object.__setattr__(self, "_s", state)

    def __setattr__(self, name: str, value: object) -> None:
        raise PermissionDeniedError(
            "CaseEngine is read-only.",
            details=(f"attempted to set {name!r}",),
            code="CASE_ENGINE_READ_ONLY",
        )

    def __delattr__(self, name: str) -> None:
        raise PermissionDeniedError(
            "CaseEngine is read-only.",
            details=(f"attempted to delete {name!r}",),
            code="CASE_ENGINE_READ_ONLY",
        )

    def __repr__(self) -> str:
        r = self._s.registry
        return (
            f"CaseEngine(case_id={r.case.case_id!r}, suspects={len(r.suspects)}, "
            f"facts={len(r.facts)}, clues={len(r.clues)}, "
            f"timeline_events={len(r.timeline_events)})"
        )

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(
        cls,
        case_id: str = "case_001",
        data_root: Path | str | None = None,
        ordering_assumptions: Iterable[OrderingAssumption] = (),
    ) -> CaseEngine:
        """Load, validate and freeze a case from disk."""
        data = load_case_data(case_id, data_root)
        if data.case.case_id != case_id:
            raise ContractValidationError(
                f"Requested case {case_id!r} but case.json declares {data.case.case_id!r}.",
                code="CASE_ID_MISMATCH",
            )
        return cls.from_case_data(data, ordering_assumptions)

    @classmethod
    def from_case_data(
        cls, data: CaseData, ordering_assumptions: Iterable[OrderingAssumption] = ()
    ) -> CaseEngine:
        """Validate already-parsed data and freeze it. Raises if it has any ERROR."""
        assumptions = tuple(ordering_assumptions)
        for item in assumptions:
            if not isinstance(item, OrderingAssumption):
                raise TypeError(
                    "ordering_assumptions must contain OrderingAssumption objects, "
                    f"got {type(item).__name__}."
                )
        report = validate_case_data(data, assumptions)
        if not report.is_valid:
            raise ContractValidationError(
                f"Case data for {data.case.case_id!r} failed validation "
                f"with {len(report.errors)} error(s).",
                details=tuple(issue.format() for issue in report.errors),
                code="CASE_DATA_INVALID",
            )
        return cls(_build_state(data, report, assumptions))

    # ----------------------------------------------------------------- metadata

    @property
    def case(self) -> Case:
        return self._s.registry.case

    @property
    def case_id(self) -> str:
        return self._s.registry.case.case_id

    @property
    def victim_id(self) -> str:
        return self._s.registry.case.victim_id

    @property
    def validation_report(self) -> ValidationReport:
        """Warnings and INFO items found at load time (there are no errors)."""
        return self._s.report

    @property
    def ordering_assumptions(self) -> tuple[OrderingAssumption, ...]:
        """Approved ordering assumptions in effect. Empty unless explicitly supplied."""
        return self._s.assumptions

    def registry(self) -> CaseRegistry:
        """The full case registry (immutable)."""
        return self._s.registry

    # ------------------------------------------------------------------ lookups

    def get_suspect(self, suspect_id: str) -> Suspect:
        return self._lookup(self._s.suspects, "suspect", suspect_id)

    def get_fact(self, fact_id: str) -> Fact:
        return self._lookup(self._s.facts, "fact", fact_id)

    def get_clue(self, clue_id: str) -> Clue:
        return self._lookup(self._s.clues, "clue", clue_id)

    def get_timeline_event(self, event_id: str) -> TimelineEvent:
        return self._lookup(self._s.events, "timeline event", event_id)

    def get_entity_reference(self, entity_id: str) -> EntityReference:
        """Resolve any entity ID used in the case (suspect, victim or external)."""
        return self._lookup(self._s.entities, "entity", entity_id)

    def list_suspects(self) -> tuple[Suspect, ...]:
        return self._s.registry.suspects

    def list_facts(self) -> tuple[Fact, ...]:
        return self._s.registry.facts

    def list_clues(self) -> tuple[Clue, ...]:
        return self._s.registry.clues

    def list_timeline_events(self) -> tuple[TimelineEvent, ...]:
        """Events in ``case.json`` order. This is *declared* order, NOT a chronology."""
        return self._s.registry.timeline_events

    def list_entity_references(self) -> tuple[EntityReference, ...]:
        return self._s.registry.entity_references

    def unregistered_entity_ids(self) -> tuple[str, ...]:
        """IDs referenced in the data that have no record anywhere (external/unresolved)."""
        return tuple(
            r.entity_id
            for r in self._s.registry.entity_references
            if r.resolution is EntityResolution.UNREGISTERED_EXTERNAL
        )

    def facts_by_category(self, category: str) -> tuple[Fact, ...]:
        return tuple(f for f in self._s.registry.facts if f.category == category)

    def facts_by_importance(self, importance: str) -> tuple[Fact, ...]:
        return tuple(f for f in self._s.registry.facts if f.importance == importance)

    def clues_by_type(self, clue_type: str) -> tuple[Clue, ...]:
        return tuple(c for c in self._s.registry.clues if c.clue_type == clue_type)

    def testimony_clues(self) -> tuple[Clue, ...]:
        """Clues the data types as ``witness_statement``.

        These record what someone SAID. They are not verified truth, whatever
        their ``reliability``. Limitation: testimony embedded in clues of other
        types (e.g. clue_019) cannot be detected from the data; see the audit.
        """
        return self.clues_by_type(TESTIMONY_CLUE_TYPE)

    # ------------------------------------------------------------ relationships

    def clues_for_fact(self, fact_id: str) -> tuple[Clue, ...]:
        """Clues whose ``related_fact_ids`` contain ``fact_id``."""
        self.get_fact(fact_id)
        return self._s.clues_by_fact[fact_id]

    def facts_for_clue(self, clue_id: str) -> tuple[Fact, ...]:
        """Facts listed in the clue's ``related_fact_ids`` (canonical fact order)."""
        self.get_clue(clue_id)
        return self._s.facts_by_clue[clue_id]

    def facts_for_suspect(self, suspect_id: str) -> tuple[Fact, ...]:
        """Facts whose ``related_entity_ids`` name the suspect. Association only."""
        self.get_suspect(suspect_id)
        return self._s.facts_by_entity[suspect_id]

    def facts_for_entity(self, entity_id: str) -> tuple[Fact, ...]:
        self.get_entity_reference(entity_id)
        return self._s.facts_by_entity[entity_id]

    def events_for_fact(self, fact_id: str) -> tuple[TimelineEvent, ...]:
        """Events whose ``related_fact_ids`` contain ``fact_id``."""
        self.get_fact(fact_id)
        return self._s.events_by_fact[fact_id]

    def facts_for_event(self, event_id: str) -> tuple[Fact, ...]:
        self.get_timeline_event(event_id)
        return self._s.facts_by_event[event_id]

    def events_for_entity(self, entity_id: str) -> tuple[TimelineEvent, ...]:
        """Events whose ``involved_entity_ids`` contain ``entity_id``."""
        self.get_entity_reference(entity_id)
        return self._s.events_by_entity[entity_id]

    def clues_sourced_from(self, entity_id: str) -> tuple[Clue, ...]:
        """Clues whose ``source_entity_id`` is ``entity_id``."""
        self.get_entity_reference(entity_id)
        return self._s.clues_by_source[entity_id]

    # ----------------------------------------------------------------- timeline

    def temporal_descriptor(self, event_id: str) -> TemporalDescriptor:
        """Raw timestamp, certainty tag and the coarse position its text states."""
        self.get_timeline_event(event_id)
        return self._s.descriptors[event_id]

    def events_by_certainty(self, certainty: TemporalCertainty) -> tuple[TimelineEvent, ...]:
        return tuple(
            e
            for e in self._s.registry.timeline_events
            if self._s.descriptors[e.timeline_event_id].certainty is certainty
        )

    def compare_events(self, first_event_id: str, second_event_id: str) -> TemporalOrdering:
        """Order two events. ``UNDETERMINED`` unless the data (or an approved
        assumption) establishes the order. Never guesses."""
        if first_event_id == second_event_id:
            raise ContractValidationError(
                "Cannot compare an event with itself.",
                details=(first_event_id,),
                code="INVALID_COMPARISON",
            )
        first = self.temporal_descriptor(first_event_id)
        second = self.temporal_descriptor(second_event_id)
        relation, basis, reason = derive_ordering(first, second)

        if relation is OrderRelation.UNDETERMINED and self._s.assumptions:
            path = self._assumption_path(first_event_id, second_event_id)
            if path is not None:
                relation, basis = OrderRelation.BEFORE, OrderBasis.APPROVED_ASSUMPTION
                reason = _assumption_reason(path)
            else:
                path = self._assumption_path(second_event_id, first_event_id)
                if path is not None:
                    relation, basis = OrderRelation.AFTER, OrderBasis.APPROVED_ASSUMPTION
                    reason = _assumption_reason(path)

        return TemporalOrdering(
            first_event_id=first_event_id,
            second_event_id=second_event_id,
            relation=relation,
            basis=basis,
            first_certainty=first.certainty,
            second_certainty=second.certainty,
            reason=reason,
        )

    def unresolved_ordering_pairs(self) -> tuple[TemporalOrdering, ...]:
        """Every pair of events whose relative order is NOT established.

        Pairs are listed once, first/second following ``case.json`` order.
        """
        events = self._s.registry.timeline_events
        pairs: list[TemporalOrdering] = []
        for i, first in enumerate(events):
            for second in events[i + 1 :]:
                result = self.compare_events(first.timeline_event_id, second.timeline_event_id)
                if result.relation is OrderRelation.UNDETERMINED:
                    pairs.append(result)
        return tuple(pairs)

    # ---------------------------------------------------------------- internals

    def _lookup(self, mapping: Mapping[str, Any], kind: str, record_id: str) -> Any:
        try:
            return mapping[record_id]
        except (KeyError, TypeError):
            raise ResourceNotFoundError(
                f"Unknown {kind} id: {record_id!r}.",
                details=(f"case_id={self.case_id}",),
            ) from None

    def _assumption_path(self, start: str, goal: str) -> tuple[OrderingAssumption, ...] | None:
        edges = self._s.assumption_edges
        queue: deque[tuple[str, tuple[OrderingAssumption, ...]]] = deque([(start, ())])
        seen = {start}
        while queue:
            node, path = queue.popleft()
            for nxt, assumption in edges.get(node, ()):
                if nxt in seen:
                    continue
                if nxt == goal:
                    return path + (assumption,)
                seen.add(nxt)
                queue.append((nxt, path + (assumption,)))
        return None


def _assumption_reason(path: tuple[OrderingAssumption, ...]) -> str:
    steps = "; ".join(
        f"{a.earlier_event_id} before {a.later_event_id} (basis: {a.basis_text!r})" for a in path
    )
    return f"Established only by approved ordering assumption(s): {steps}."


def _ro(mapping: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(mapping)


def _build_state(
    data: CaseData, report: ValidationReport, assumptions: tuple[OrderingAssumption, ...]
) -> _State:
    case = data.case
    suspects_by_id = {s.suspect_id: s for s in data.suspects}
    facts_by_id = {f.fact_id: f for f in data.facts}
    clues_by_id = {c.clue_id: c for c in data.clues}
    events_by_id = {e.timeline_event_id: e for e in data.timeline_events}

    # Canonical order = the ID order in case.json.
    suspects = tuple(suspects_by_id[i] for i in case.suspect_ids)
    facts = tuple(facts_by_id[i] for i in case.fact_ids)
    clues = tuple(clues_by_id[i] for i in case.clue_ids)
    events = tuple(events_by_id[i] for i in case.timeline_event_ids)
    fact_pos = {f.fact_id: i for i, f in enumerate(facts)}

    # Entity registry: suspects, victim, then external IDs by first appearance.
    suspect_ids = frozenset(case.suspect_ids)
    entities: dict[str, EntityReference] = {}

    def register(entity_id: str) -> None:
        if entity_id not in entities:
            entities[entity_id] = classify_entity_id(entity_id, suspect_ids, case.victim_id)

    for suspect in suspects:
        register(suspect.suspect_id)
    register(case.victim_id)
    for fact in facts:
        for entity_id in fact.related_entity_ids:
            register(entity_id)
    for clue in clues:
        if clue.source_entity_id is not None:
            register(clue.source_entity_id)
    for event in events:
        for entity_id in event.involved_entity_ids:
            register(entity_id)

    def ordered_facts(fact_ids: Iterable[str]) -> tuple[Fact, ...]:
        return tuple(facts_by_id[i] for i in sorted(set(fact_ids), key=fact_pos.__getitem__))

    clues_by_fact: dict[str, list[Clue]] = {f.fact_id: [] for f in facts}
    facts_by_clue: dict[str, tuple[Fact, ...]] = {}
    for clue in clues:
        facts_by_clue[clue.clue_id] = ordered_facts(clue.related_fact_ids)
        for fact_id in clue.related_fact_ids:
            clues_by_fact[fact_id].append(clue)

    events_by_fact: dict[str, list[TimelineEvent]] = {f.fact_id: [] for f in facts}
    facts_by_event: dict[str, tuple[Fact, ...]] = {}
    events_by_entity: dict[str, list[TimelineEvent]] = {e: [] for e in entities}
    for event in events:
        facts_by_event[event.timeline_event_id] = ordered_facts(event.related_fact_ids)
        for fact_id in event.related_fact_ids:
            events_by_fact[fact_id].append(event)
        for entity_id in event.involved_entity_ids:
            events_by_entity[entity_id].append(event)

    facts_by_entity: dict[str, list[Fact]] = {e: [] for e in entities}
    for fact in facts:
        for entity_id in fact.related_entity_ids:
            facts_by_entity[entity_id].append(fact)

    clues_by_source: dict[str, list[Clue]] = {e: [] for e in entities}
    for clue in clues:
        if clue.source_entity_id is not None:
            clues_by_source[clue.source_entity_id].append(clue)

    edges: dict[str, list[tuple[str, OrderingAssumption]]] = {}
    for a in assumptions:
        edges.setdefault(a.earlier_event_id, []).append((a.later_event_id, a))

    registry = CaseRegistry(
        case=case,
        suspects=suspects,
        facts=facts,
        clues=clues,
        timeline_events=events,
        entity_references=tuple(entities.values()),
    )
    return _State(
        registry=registry,
        report=report,
        assumptions=assumptions,
        suspects=_ro(suspects_by_id),
        facts=_ro(facts_by_id),
        clues=_ro(clues_by_id),
        events=_ro(events_by_id),
        entities=_ro(entities),
        descriptors=_ro({e.timeline_event_id: parse_timestamp(e.timestamp) for e in events}),
        clues_by_fact=_ro({k: tuple(v) for k, v in clues_by_fact.items()}),
        facts_by_clue=_ro(facts_by_clue),
        events_by_fact=_ro({k: tuple(v) for k, v in events_by_fact.items()}),
        facts_by_event=_ro(facts_by_event),
        facts_by_entity=_ro({k: tuple(v) for k, v in facts_by_entity.items()}),
        events_by_entity=_ro({k: tuple(v) for k, v in events_by_entity.items()}),
        clues_by_source=_ro({k: tuple(v) for k, v in clues_by_source.items()}),
        assumption_edges=_ro({k: tuple(v) for k, v in edges.items()}),
    )
