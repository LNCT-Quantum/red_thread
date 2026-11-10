

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "TemporalCertainty",
    "TemporalFrame",
    "OrderRelation",
    "OrderBasis",
    "StatedOffset",
    "TemporalDescriptor",
    "TemporalOrdering",
    "OrderingAssumption",
    "parse_timestamp",
    "derive_ordering",
]


class TemporalCertainty(str, Enum):
    """Certainty tag found at the end of every ``timeline.json`` timestamp.

    The vocabulary is closed to the four tags present in case_001. There is
    deliberately no ``EXACT`` member: no event in the source is exact.
    """

    APPROXIMATE = "approximate"
    ESTIMATED = "estimated"
    UNVERIFIED = "unverified"
    UNDETERMINED = "undetermined"


class TemporalFrame(str, Enum):
    """Coarse position the timestamp text itself states."""

    PRE_DAY_1 = "pre_day_1"
    DAY_1 = "day_1"
    DAY_1_TO_DAY_4 = "day_1_to_day_4"
    UNANCHORED = "unanchored"  # text does not place the event relative to Day 1


class OrderRelation(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    UNDETERMINED = "undetermined"


class OrderBasis(str, Enum):
    STATED_OFFSET = "stated_offset"
    STATED_FRAME = "stated_frame"
    APPROVED_ASSUMPTION = "approved_assumption"
    NOT_ESTABLISHED = "not_established"


@dataclass(frozen=True, slots=True)
class StatedOffset:
    """An offset before Day 1 as stated, normalised only as years -> months."""

    months: int
    days: int = 0

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.months, self.days)


@dataclass(frozen=True, slots=True)
class TemporalDescriptor:
    raw: str  # exactly as in timeline.json
    text: str  # raw without the trailing [tag]
    certainty: TemporalCertainty
    frame: TemporalFrame
    offset_before_day_1: StatedOffset | None


@dataclass(frozen=True, slots=True)
class TemporalOrdering:
    """Result of comparing two events.

    ``relation`` describes ``first_event_id`` relative to ``second_event_id``.
    The two certainties are carried alongside so a caller can never mistake an
    established order between two *approximate* events for an exact one.
    """

    first_event_id: str
    second_event_id: str
    relation: OrderRelation
    basis: OrderBasis
    first_certainty: TemporalCertainty
    second_certainty: TemporalCertainty
    reason: str


@dataclass(frozen=True, slots=True)
class OrderingAssumption:
    """A human-approved ordering edge: ``earlier_event_id`` precedes ``later_event_id``.

    ``basis_text`` must quote the source wording that motivates the edge; the
    validator does not enforce that, but the proposals test-suite does.
    """

    earlier_event_id: str
    later_event_id: str
    basis_text: str

    def __post_init__(self) -> None:
        for name in ("earlier_event_id", "later_event_id", "basis_text"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"'{name}' must be a str, got {type(value).__name__}.")
            if not value.strip():
                raise ValueError(f"'{name}' must not be empty or whitespace.")


_TAG_RE = re.compile(r"^(?P<text>.*\S)\s*\[(?P<tag>[^\[\]]+)\]$")
_OFFSET_RE = re.compile(
    r"^approx\. (?P<n>\d+) (?P<unit>years?|months?)"
    r"(?: and (?P<d>\d+) days?)? before Day 1$"
)
_BEFORE_DAY_1_RE = re.compile(r"\bbefore Day 1\b")
_DAY_1_TO_4_RE = re.compile(r"^Day 1 to Day 4\b")
_DAY_1_RE = re.compile(r"^Day 1\b")


def parse_timestamp(raw: str) -> TemporalDescriptor:
    """Parse a timeline timestamp. Raise ``ValueError`` if it has no valid tag.

    A timestamp without a recognised certainty tag is rejected rather than
    assumed exact.
    """
    if not isinstance(raw, str):
        raise TypeError(f"timestamp must be a str, got {type(raw).__name__}.")

    match = _TAG_RE.match(raw.strip())
    if match is None:
        raise ValueError(
            f"timestamp {raw!r} has no trailing certainty tag such as "
            "[approximate]; it cannot be treated as exact."
        )
    tag = match.group("tag")
    try:
        certainty = TemporalCertainty(tag)
    except ValueError:
        allowed = ", ".join(f"[{c.value}]" for c in TemporalCertainty)
        raise ValueError(
            f"timestamp {raw!r} has unrecognised certainty tag [{tag}]; "
            f"expected one of {allowed}."
        ) from None

    text = match.group("text")
    frame, offset = _interpret_text(text)
    return TemporalDescriptor(
        raw=raw,
        text=text,
        certainty=certainty,
        frame=frame,
        offset_before_day_1=offset,
    )


def _interpret_text(text: str) -> tuple[TemporalFrame, StatedOffset | None]:
    if _DAY_1_TO_4_RE.match(text):
        return TemporalFrame.DAY_1_TO_DAY_4, None
    if _DAY_1_RE.match(text):
        return TemporalFrame.DAY_1, None

    offset_match = _OFFSET_RE.match(text)
    if offset_match is not None:
        quantity = int(offset_match.group("n"))
        months = quantity * 12 if offset_match.group("unit").startswith("year") else quantity
        days = int(offset_match.group("d") or 0)
        # Mixing months and a day count is only comparable when the days are
        # less than a month; otherwise decline to quantify.
        if days > 27:
            return TemporalFrame.PRE_DAY_1, None
        return TemporalFrame.PRE_DAY_1, StatedOffset(months=months, days=days)

    if _BEFORE_DAY_1_RE.search(text):
        return TemporalFrame.PRE_DAY_1, None  # e.g. "years before Day 1; start date unknown"
    return TemporalFrame.UNANCHORED, None


_DAY_FRAMES = frozenset({TemporalFrame.DAY_1, TemporalFrame.DAY_1_TO_DAY_4})


def derive_ordering(
    first: TemporalDescriptor, second: TemporalDescriptor
) -> tuple[OrderRelation, OrderBasis, str]:
    """Order two events using only what their timestamps state (no assumptions)."""
    first_pre = first.frame is TemporalFrame.PRE_DAY_1
    second_pre = second.frame is TemporalFrame.PRE_DAY_1

    if first_pre and second_pre:
        a, b = first.offset_before_day_1, second.offset_before_day_1
        if a is None or b is None:
            return (
                OrderRelation.UNDETERMINED,
                OrderBasis.NOT_ESTABLISHED,
                "At least one event states no quantified offset before Day 1.",
            )
        if a.sort_key == b.sort_key:
            return (
                OrderRelation.UNDETERMINED,
                OrderBasis.NOT_ESTABLISHED,
                "Both events state the same offset before Day 1; their order "
                "relative to each other is not established.",
            )
        relation = OrderRelation.BEFORE if a.sort_key > b.sort_key else OrderRelation.AFTER
        return (
            relation,
            OrderBasis.STATED_OFFSET,
            "Ordered by the stated (approximate) offsets before Day 1; the "
            "larger offset is earlier.",
        )

    if first_pre and second.frame in _DAY_FRAMES:
        return (
            OrderRelation.BEFORE,
            OrderBasis.STATED_FRAME,
            "First event is stated to be before Day 1; second is stated to be on Day 1.",
        )
    if second_pre and first.frame in _DAY_FRAMES:
        return (
            OrderRelation.AFTER,
            OrderBasis.STATED_FRAME,
            "Second event is stated to be before Day 1; first is stated to be on Day 1.",
        )

    if first.frame in _DAY_FRAMES and second.frame in _DAY_FRAMES:
        reason = (
            "Both events are placed on Day 1 (or Day 1 to Day 4); the source "
            "does not state their order within it."
        )
    else:
        reason = (
            "The timestamp text of at least one event does not place it "
            "relative to Day 1, so no order is established."
        )
    return OrderRelation.UNDETERMINED, OrderBasis.NOT_ESTABLISHED, reason
