
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "EntityResolution",
    "EntityReference",
    "RESERVED_ID_PREFIXES",
    "EXTERNAL_ID_PREFIXES",
    "classify_entity_id",
]

RESERVED_ID_PREFIXES: frozenset[str] = frozenset(
    {"suspect_", "victim_", "fact_", "clue_", "event_"}
)
EXTERNAL_ID_PREFIXES: frozenset[str] = frozenset(
    {"entity_", "object_", "location_", "player_"}
)


class EntityResolution(str, Enum):
    SUSPECT = "suspect"  # resolves to a Suspect record
    VICTIM = "victim"  # equals Case.victim_id; no victim record exists
    UNREGISTERED_EXTERNAL = "unregistered_external"  # referenced, no record


@dataclass(frozen=True, slots=True)
class EntityReference:
    entity_id: str
    resolution: EntityResolution
    prefix_hint: str  # text before the first underscore; a hint, not a type


def classify_entity_id(
    entity_id: str, suspect_ids: Collection[str], victim_id: str
) -> EntityReference:
    """Classify ``entity_id`` or raise ``ValueError`` explaining why it cannot be."""
    prefix = entity_id.split("_", 1)[0]
    if entity_id in suspect_ids:
        return EntityReference(entity_id, EntityResolution.SUSPECT, prefix)
    if entity_id == victim_id:
        return EntityReference(entity_id, EntityResolution.VICTIM, prefix)

    marker = f"{prefix}_"
    if marker in RESERVED_ID_PREFIXES:
        raise ValueError(
            f"{entity_id!r} uses the reserved prefix {marker!r} but does not "
            "match any registered record."
        )
    if marker in EXTERNAL_ID_PREFIXES:
        return EntityReference(entity_id, EntityResolution.UNREGISTERED_EXTERNAL, prefix)
    raise ValueError(
        f"{entity_id!r} has an unrecognised prefix; it can be classified "
        "neither as a registered record nor as an external reference."
    )
