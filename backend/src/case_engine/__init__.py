"""Red Thread Case Engine: deterministic, read-only source of truth for a case.

Typical use::

    from src.case_engine import CaseEngine

    engine = CaseEngine.load("case_001")
    engine.get_fact("fact_003")
    engine.clues_for_fact("fact_003")

See ``backend/docs/case_engine/README.md``.
"""

from .engine import TESTIMONY_CLUE_TYPE, CaseEngine, CaseRegistry
from .entities import EntityReference, EntityResolution
from .loader import CaseData, load_case_data
from .proposals import PROPOSED_ORDERING_ASSUMPTIONS
from .temporal import (
    OrderBasis,
    OrderingAssumption,
    OrderRelation,
    StatedOffset,
    TemporalCertainty,
    TemporalDescriptor,
    TemporalFrame,
    TemporalOrdering,
)
from .timeline import TimelineEvent
from .validation import Severity, ValidationIssue, ValidationReport, validate_case_data

__all__ = [
    "CaseEngine",
    "CaseRegistry",
    "CaseData",
    "load_case_data",
    "TimelineEvent",
    "EntityReference",
    "EntityResolution",
    "TemporalCertainty",
    "TemporalFrame",
    "TemporalDescriptor",
    "TemporalOrdering",
    "StatedOffset",
    "OrderRelation",
    "OrderBasis",
    "OrderingAssumption",
    "PROPOSED_ORDERING_ASSUMPTIONS",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "validate_case_data",
    "TESTIMONY_CLUE_TYPE",
]
