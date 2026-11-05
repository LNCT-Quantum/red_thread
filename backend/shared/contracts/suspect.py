

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Suspect"]


@dataclass(frozen=True, slots=True)
class Suspect:
    suspect_id: str
    name: str
    occupation: str
    background: str
    public_description: str
    relationship_to_victim: str
    speech_style: str
    age: int | None = None
    personality_traits: tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "suspect_id",
            "name",
            "occupation",
            "background",
            "public_description",
            "relationship_to_victim",
            "speech_style",
            "schema_version",
        ):
            self._validate_required_string(field_name, getattr(self, field_name))

        self._validate_age(self.age)
        self._validate_personality_traits(self.personality_traits)

    @staticmethod
    def _validate_required_string(field_name: str, value: object) -> None:
        """Ensure ``value`` is a non-empty, non-whitespace string."""
        if not isinstance(value, str):
            raise TypeError(
                f"'{field_name}' must be a str, got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(f"'{field_name}' must not be empty or whitespace.")

    @staticmethod
    def _validate_age(value: object) -> None:
        """Ensure ``value`` is ``None`` or a positive integer (not a bool)."""
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"'age' must be an int or None, got {type(value).__name__}."
            )
        if value <= 0:
            raise ValueError(f"'age' must be a positive integer, got {value}.")

    @staticmethod
    def _validate_personality_traits(value: object) -> None:
        """Ensure ``value`` is a tuple of unique, non-blank string traits."""
        if not isinstance(value, tuple):
            raise TypeError(
                "'personality_traits' must be a tuple, "
                f"got {type(value).__name__}."
            )

        seen: set[str] = set()
        for index, trait in enumerate(value):
            if not isinstance(trait, str):
                raise TypeError(
                    f"'personality_traits[{index}]' must be a str, "
                    f"got {type(trait).__name__}."
                )
            if not trait.strip():
                raise ValueError(
                    f"'personality_traits[{index}]' must not be empty "
                    "or whitespace."
                )
            if trait in seen:
                raise ValueError(
                    f"'personality_traits' contains duplicate trait: {trait!r}."
                )
            seen.add(trait)