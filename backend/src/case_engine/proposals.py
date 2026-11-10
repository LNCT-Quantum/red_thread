

from __future__ import annotations

from .temporal import OrderingAssumption

__all__ = ["PROPOSED_ORDERING_ASSUMPTIONS"]

PROPOSED_ORDERING_ASSUMPTIONS: tuple[OrderingAssumption, ...] = (
    OrderingAssumption("event_007", "event_011", "before Rishabh's death"),
    OrderingAssumption("event_008", "event_011", "about 3 hours before death"),
    OrderingAssumption("event_011", "event_013", "after the death"),
    OrderingAssumption("event_013", "event_014", "after the discovery"),
)
