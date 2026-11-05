from __future__ import annotations

__all__ = [
    "RedThreadError",
    "ContractValidationError",
    "ResourceNotFoundError",
    "PermissionDeniedError",
    "StateConflictError",
    "ExternalServiceError",
]


class RedThreadError(Exception):

    default_code: str = "RED_THREAD_ERROR"

    def __init__(
        self,
        message: str,
        details: tuple[str, ...] = (),
        code: str | None = None,
    ) -> None:
        self._validate_required_string("message", message)
        self._validate_details(details)

        resolved_code = self.default_code if code is None else code
        self._validate_required_string("code", resolved_code)

        super().__init__(message)
        self.message: str = message
        self.code: str = resolved_code
        self.details: tuple[str, ...] = details

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
    def _validate_details(value: object) -> None:
        """Ensure ``value`` is a tuple of non-empty, non-blank strings."""
        if not isinstance(value, tuple):
            raise TypeError(
                f"'details' must be a tuple, got {type(value).__name__}."
            )
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

    def __str__(self) -> str:
        """Return the error as ``[CODE] message`` with optional details."""
        text = f"[{self.code}] {self.message}"
        if self.details:
            text = f"{text} ({'; '.join(self.details)})"
        return text

    def __repr__(self) -> str:
        """Return an unambiguous representation of the error."""
        return (
            f"{type(self).__name__}(message={self.message!r}, "
            f"details={self.details!r}, code={self.code!r})"
        )


class ContractValidationError(RedThreadError):


    default_code = "CONTRACT_VALIDATION_ERROR"


class ResourceNotFoundError(RedThreadError):
    """Raised when a requested case, suspect, clue, fact, or other resource
    does not exist."""

    default_code = "RESOURCE_NOT_FOUND"


class PermissionDeniedError(RedThreadError):
    """Raised when a module or user attempts an operation it is not
    authorized to perform."""

    default_code = "PERMISSION_DENIED"


class StateConflictError(RedThreadError):
    """Raised when an operation conflicts with the current game or
    application state."""

    default_code = "STATE_CONFLICT"


class ExternalServiceError(RedThreadError):
    """Raised when an external dependency or service fails."""

    default_code = "EXTERNAL_SERVICE_ERROR"