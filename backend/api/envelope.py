"""Response envelope built on ``shared.contracts.api`` plus JSON serialization.

Every response, success or failure, is an ``APIResponse`` contract object turned into
plain JSON here, so the frontend always receives the same shape::

    {"request_id", "success", "data", "error": {"code","message","details"}, "schema_version"}
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.contracts.api import APIError, APIResponse

__all__ = ["to_jsonable", "success", "failure"]


def to_jsonable(value: Any) -> Any:
    """Convert contracts, pydantic models, enums, tuples and datetimes into JSON types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable.")


def success(
    request_id: str,
    data: Any,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response = APIResponse(request_id=request_id, success=True, data=data)
    return JSONResponse(to_jsonable(response), status_code=status_code, headers=dict(headers or {}))


def failure(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    details: tuple[str, ...] | list[str] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    # APIError rejects blank and duplicate details, so normalise them first.
    cleaned = tuple(dict.fromkeys(item.strip() for item in details if item and item.strip()))
    response = APIResponse(
        request_id=request_id,
        success=False,
        error=APIError(code=code, message=message, details=cleaned),
    )
    return JSONResponse(to_jsonable(response), status_code=status_code, headers=dict(headers or {}))
