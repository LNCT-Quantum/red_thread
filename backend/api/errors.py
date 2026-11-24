"""Error translation: domain exceptions -> stable, safe API errors.

Domain exceptions (``shared.contracts.errors``) may carry details that must never reach a
client (filesystem paths, unmet progression requirements, hidden clue/fact IDs). Only the
codes listed in ``_RULES`` get a specific public message, and details are forwarded only
where a rule explicitly allows it. Everything else falls back to a generic message by
exception class.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.contracts.errors import (
    ContractValidationError,
    ExternalServiceError,
    PermissionDeniedError,
    RedThreadError,
    ResourceNotFoundError,
    StateConflictError,
)

from .envelope import failure

__all__ = ["ApiError", "translate_domain_error", "register_exception_handlers"]

log = logging.getLogger("redthread.api.errors")


class ApiError(Exception):
    """An error that maps 1:1 onto an HTTP status and an envelope ``error`` object."""

    def __init__(
        self, status_code: int, code: str, message: str, details: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = tuple(details)


@dataclass(frozen=True, slots=True)
class _Rule:
    status: int
    code: str
    message: str
    forward_details: bool = False


_INVALID_STATE = _Rule(500, "SESSION_STATE_INVALID", "The stored game session is inconsistent")

_RULES: dict[str, _Rule] = {
    "GAME_SESSION_NOT_FOUND": _Rule(404, "SESSION_NOT_FOUND", "The requested session does not exist"),
    "CASE_NOT_FOUND": _Rule(404, "CASE_NOT_FOUND", "The requested case does not exist"),
    "CLUE_WRONG_CASE": _Rule(404, "CLUE_NOT_FOUND", "The requested clue does not exist"),
    "REVISION_CONFLICT": _Rule(
        409,
        "REVISION_CONFLICT",
        "The game state was changed by another request. Reload the session and try again",
        forward_details=True,
    ),
    "GAME_NOT_ACTIVE": _Rule(409, "GAME_NOT_ACTIVE", "The game session is no longer active", True),
    "CLUE_LOCKED": _Rule(403, "CLUE_LOCKED", "This clue is not available yet"),
    "CLUE_ALREADY_DISCOVERED": _Rule(409, "CLUE_ALREADY_DISCOVERED", "This clue was already discovered"),
    "CLUE_NOT_DISCOVERED": _Rule(
        403, "CLUE_NOT_DISCOVERED", "Only clues you have discovered can be presented"
    ),
    "PRESENTED_CLUE_DUPLICATE": _Rule(
        400, "INVALID_REQUEST", "The same clue cannot be presented twice in one message"
    ),
    "DIALOGUE_TURN_STALE": _Rule(
        409,
        "DIALOGUE_TURN_STALE",
        "The game state changed while the suspect was answering. Please ask again",
    ),
    "DIALOGUE_MESSAGE_OUT_OF_ORDER": _Rule(409, "STATE_CONFLICT", "The conversation changed. Reload and retry"),
    "DIALOGUE_MESSAGE_ID_CONFLICT": _Rule(409, "STATE_CONFLICT", "The conversation changed. Reload and retry"),
    "GAME_STATE_CASE_MISMATCH": _INVALID_STATE,
    "GAME_STATE_FOREIGN_ID": _INVALID_STATE,
    "STAGE_MARKER_UNKNOWN": _INVALID_STATE,
    "STAGE_SKIP_DETECTED": _INVALID_STATE,
    "REVISION_INVALID": _INVALID_STATE,
    "DIALOGUE_HISTORY_REWRITTEN": _INVALID_STATE,
    "SESSION_CASE_CHANGED": _INVALID_STATE,
}


def translate_domain_error(exc: RedThreadError) -> ApiError:
    """Map a Red Thread domain exception onto a safe ``ApiError``."""
    rule = _RULES.get(exc.code)
    if rule is not None:
        if rule.status >= 500:
            log.error("domain error %s: %s %s", exc.code, exc.message, exc.details)
        return ApiError(
            rule.status, rule.code, rule.message, exc.details if rule.forward_details else ()
        )
    if isinstance(exc, ResourceNotFoundError):
        return ApiError(404, "RESOURCE_NOT_FOUND", "The requested resource does not exist")
    if isinstance(exc, PermissionDeniedError):
        return ApiError(403, "ACCESS_DENIED", "This action is not allowed at the current point of the investigation")
    if isinstance(exc, StateConflictError):
        return ApiError(409, "STATE_CONFLICT", "The request conflicts with the current game state")
    if isinstance(exc, ContractValidationError):
        return ApiError(400, "INVALID_REQUEST", "The request could not be processed")
    if isinstance(exc, ExternalServiceError):
        return ApiError(503, "SERVICE_UNAVAILABLE", "A required service is unavailable")
    log.error("unmapped domain error %s: %s %s", exc.code, exc.message, exc.details)
    return ApiError(500, "INTERNAL_ERROR", "An unexpected error occurred")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def register_exception_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return failure(_request_id(request), exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RedThreadError)
    async def _domain_error(request: Request, exc: RedThreadError):
        api_error = translate_domain_error(exc)
        return failure(
            _request_id(request),
            api_error.status_code,
            api_error.code,
            api_error.message,
            api_error.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(item.get("type") == "json_invalid" for item in errors):
            return failure(
                _request_id(request), 400, "INVALID_JSON", "The request body is not valid JSON"
            )
        details = [
            f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('msg', 'invalid value')}"
            for item in errors
        ]
        return failure(
            _request_id(request), 422, "REQUEST_VALIDATION_ERROR", "The request failed validation", details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        table = {
            404: ("ROUTE_NOT_FOUND", "The requested endpoint does not exist"),
            405: ("METHOD_NOT_ALLOWED", "This HTTP method is not allowed for the endpoint"),
        }
        code, message = table.get(exc.status_code, ("HTTP_ERROR", "The request could not be completed"))
        return failure(_request_id(request), exc.status_code, code, message)
