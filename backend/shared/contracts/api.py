

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

__all__ = ["APIError", "APIResponse"]

T = TypeVar("T")


def _validate_required_string(field_name: str, value: object) -> None:
    """Ensure ``value`` is a non-empty, non-whitespace string."""
    if not isinstance(value, str):
        raise TypeError(
            f"'{field_name}' must be a str, got {type(value).__name__}."
        )
    if not value.strip():
        raise ValueError(f"'{field_name}' must not be empty or whitespace.")


@dataclass(frozen=True, slots=True)
class APIError:

    code: str
    message: str
    details: tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in ("code", "message", "schema_version"):
            _validate_required_string(field_name, getattr(self, field_name))

        self._validate_details(self.details)

    @staticmethod
    def _validate_details(value: object) -> None:
        """Ensure ``value`` is a tuple of unique, non-blank strings."""
        if not isinstance(value, tuple):
            raise TypeError(
                f"'details' must be a tuple, got {type(value).__name__}."
            )

        seen: set[str] = set()
        for index, detail in enumerate(value):
            if not isinstance(detail, str):
                raise TypeError(
                    f"'details[{index}]' must be a str, "
                    f"got {type(detail).__name__}."
                )
            if not detail.strip():
                raise ValueError(
                    f"'details[{index}]' must not be empty or whitespace."
                )
            if detail in seen:
                raise ValueError(
                    f"'details' contains duplicate entry: {detail!r}."
                )
            seen.add(detail)


@dataclass(frozen=True, slots=True)
class APIResponse(Generic[T]):


    request_id: str
    success: bool
    data: T | None = None
    error: APIError | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate all fields after initialization."""
        for field_name in ("request_id", "schema_version"):
            _validate_required_string(field_name, getattr(self, field_name))

        self._validate_success(self.success)
        self._validate_error(self.error)
        self._validate_consistency(self.success, self.data, self.error)

    @staticmethod
    def _validate_success(value: object) -> None:
        """Ensure ``value`` is a boolean."""
        if not isinstance(value, bool):
            raise TypeError(
                f"'success' must be a bool, got {type(value).__name__}."
            )

    @staticmethod
    def _validate_error(value: object) -> None:
        """Ensure ``value`` is ``None`` or an ``APIError`` instance."""
        if value is not None and not isinstance(value, APIError):
            raise TypeError(
                "'error' must be an APIError or None, "
                f"got {type(value).__name__}."
            )

    @staticmethod
    def _validate_consistency(
        success: bool, data: object, error: APIError | None
    ) -> None:
        """Ensure ``data`` and ``error`` agree with the ``success`` flag."""
        if success:
            if error is not None:
                raise ValueError(
                    "'error' must be None when 'success' is True."
                )
            return

        if error is None:
            raise ValueError(
                "'error' must be an APIError when 'success' is False."
            )
        if data is not None:
            raise ValueError("'data' must be None when 'success' is False.")