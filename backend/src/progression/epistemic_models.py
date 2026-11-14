
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


__all__ = ["BeliefStatus", "NpcBelief"]


class BeliefStatus(str, Enum):
    """An NPC's stance toward a proposition, not objective truth."""

    SUSPECTS = "suspects"
    BELIEVES = "believes"
    DOUBTS = "doubts"
    REJECTS = "rejects"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class NpcBelief:
    """Static authored belief metadata, kept separate from canonical facts."""

    belief_id: str
    suspect_id: str
    proposition: str
    status: BeliefStatus = BeliefStatus.UNCERTAIN
    confidence: float = 0.5
    source_note: str = ""
    target_fact_id: str | None = None
    basis_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("belief_id", "suspect_id", "proposition"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(
                    f"'{name}' must be a str, got {type(value).__name__}."
                )
            if not value.strip():
                raise ValueError(
                    f"'{name}' must not be empty or whitespace."
                )

        if not isinstance(self.source_note, str):
            raise TypeError("'source_note' must be a str.")

        if not isinstance(self.status, BeliefStatus):
            try:
                object.__setattr__(
                    self, "status", BeliefStatus(self.status)
                )
            except (TypeError, ValueError) as exc:
                allowed = ", ".join(
                    item.value for item in BeliefStatus
                )
                raise ValueError(
                    f"'status' must be one of {allowed}."
                ) from exc

        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
        ):
            raise TypeError(
                "'confidence' must be a number between 0.0 and 1.0."
            )

        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(
                "'confidence' must be between 0.0 and 1.0."
            )

        object.__setattr__(
            self, "confidence", float(self.confidence)
        )

        if self.target_fact_id is not None:
            if (
                not isinstance(self.target_fact_id, str)
                or not self.target_fact_id.strip()
            ):
                raise ValueError(
                    "'target_fact_id' must be a non-empty string or None."
                )

        if not isinstance(self.basis_fact_ids, tuple):
            raise TypeError("'basis_fact_ids' must be a tuple.")

        seen: set[str] = set()

        for index, fact_id in enumerate(self.basis_fact_ids):
            if not isinstance(fact_id, str) or not fact_id.strip():
                raise ValueError(
                    f"'basis_fact_ids[{index}]' must be a non-empty string."
                )

            if fact_id in seen:
                raise ValueError(
                    f"duplicate basis fact ID: {fact_id!r}."
                )

            seen.add(fact_id)
