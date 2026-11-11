
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


__all__ = [
    "ProgressionStage",
    "Progression",
]


def _validate_required_string(value: str, field_name: str) -> None:
    """Validate a required non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _validate_id_tuple(
    values: tuple[str, ...],
    field_name: str,
) -> None:
    """Validate a tuple of unique, non-empty ID strings."""
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")

    seen: set[str] = set()

    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Every entry in {field_name} must be a non-empty string."
            )

        if value in seen:
            raise ValueError(
                f"Duplicate ID '{value}' found in {field_name}."
            )

        seen.add(value)


@dataclass(frozen=True, slots=True)
class ProgressionStage:
    """
    Defines a single investigation stage.

    A stage specifies the conditions required to enter it
    and the clues/facts that become available upon reaching it.
    """

    stage_id: str
    title: str
    description: str

    required_clue_ids: tuple[str, ...] = ()
    required_interviewed_suspect_ids: tuple[str, ...] = ()

    unlocks_clue_ids: tuple[str, ...] = ()
    unlocks_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_required_string(self.stage_id, "stage_id")
        _validate_required_string(self.title, "title")
        _validate_required_string(self.description, "description")

        _validate_id_tuple(
            self.required_clue_ids,
            "required_clue_ids",
        )

        _validate_id_tuple(
            self.required_interviewed_suspect_ids,
            "required_interviewed_suspect_ids",
        )

        _validate_id_tuple(
            self.unlocks_clue_ids,
            "unlocks_clue_ids",
        )

        _validate_id_tuple(
            self.unlocks_fact_ids,
            "unlocks_fact_ids",
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProgressionStage:
        """Construct a stage from progression JSON data."""

        if not isinstance(data, Mapping):
            raise TypeError("Progression stage data must be a mapping.")

        def get_ids(key: str) -> tuple[str, ...]:
            values = data.get(key, [])

            if not isinstance(values, (list, tuple)):
                raise TypeError(f"{key} must be a list or tuple.")

            return tuple(values)

        return cls(
            stage_id=data.get("stage_id"),
            title=data.get("title"),
            description=data.get("description"),
            required_clue_ids=get_ids("required_clue_ids"),
            required_interviewed_suspect_ids=get_ids(
                "required_interviewed_suspect_ids"
            ),
            unlocks_clue_ids=get_ids("unlocks_clue_ids"),
            unlocks_fact_ids=get_ids("unlocks_fact_ids"),
        )


@dataclass(frozen=True, slots=True)
class Progression:
    """
    Defines the complete investigation progression for a case.

    Stages are ordered. Their position in the stages tuple
    determines their investigation sequence.
    """

    stages: tuple[ProgressionStage, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.stages, tuple):
            raise TypeError("stages must be a tuple.")

        if not self.stages:
            raise ValueError(
                "Progression must contain at least one stage."
            )

        seen_stage_ids: set[str] = set()

        for stage in self.stages:
            if not isinstance(stage, ProgressionStage):
                raise TypeError(
                    "Every stage must be a ProgressionStage instance."
                )

            if stage.stage_id in seen_stage_ids:
                raise ValueError(
                    f"Duplicate stage_id '{stage.stage_id}'."
                )

            seen_stage_ids.add(stage.stage_id)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Progression:
        """Construct progression from a parsed JSON dictionary."""

        if not isinstance(data, Mapping):
            raise TypeError("Progression data must be a mapping.")

        raw_stages = data.get("stages")

        if not isinstance(raw_stages, list):
            raise TypeError("Progression 'stages' must be a list.")

        stages = tuple(
            ProgressionStage.from_dict(stage)
            for stage in raw_stages
        )

        return cls(stages=stages)

    @classmethod
    def from_json(cls, json_data: str) -> Progression:
        """Construct progression directly from a JSON string."""

        if not isinstance(json_data, str):
            raise TypeError("json_data must be a string.")

        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid progression JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                "Progression JSON root must be an object."
            )

        return cls.from_dict(data)

    @property
    def first_stage(self) -> ProgressionStage:
        """Return the initial investigation stage."""
        return self.stages[0]

    @property
    def final_stage(self) -> ProgressionStage:
        """Return the final investigation stage."""
        return self.stages[-1]

    def get_stage(self, stage_id: str) -> ProgressionStage | None:
        """Retrieve a stage using its ID."""

        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage

        return None

    def get_stage_index(self, stage_id: str) -> int | None:
        """Return the zero-based position of a stage."""

        for index, stage in enumerate(self.stages):
            if stage.stage_id == stage_id:
                return index

        return None

    def get_next_stage(
        self,
        stage_id: str,
    ) -> ProgressionStage | None:
        """Return the stage immediately following the given stage."""

        index = self.get_stage_index(stage_id)

        if index is None or index >= len(self.stages) - 1:
            return None

        return self.stages[index + 1]

    def has_stage(self, stage_id: str) -> bool:
        """Check whether a stage exists."""
        return self.get_stage(stage_id) is not None
