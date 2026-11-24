"""Shared route helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path

from ..schemas.responses import ApiEnvelope

# IDs are only ever used as dictionary keys, but bound their size anyway.
SessionIdPath = Annotated[str, Path(min_length=1, max_length=128, description="Session ID from POST /sessions.")]
CaseIdPath = Annotated[str, Path(min_length=1, max_length=128, description="Case ID from GET /cases.")]
ClueIdPath = Annotated[str, Path(min_length=1, max_length=128)]
SuspectIdPath = Annotated[str, Path(min_length=1, max_length=128)]

#: Error envelopes documented on every endpoint.
ERROR_RESPONSES = {
    400: {"model": ApiEnvelope[None], "description": "Invalid request"},
    403: {"model": ApiEnvelope[None], "description": "Action not allowed yet"},
    404: {"model": ApiEnvelope[None], "description": "Resource not found"},
    409: {"model": ApiEnvelope[None], "description": "State or revision conflict"},
    422: {"model": ApiEnvelope[None], "description": "Request validation failure"},
    500: {"model": ApiEnvelope[None], "description": "Unexpected internal error"},
    503: {"model": ApiEnvelope[None], "description": "Required service unavailable"},
}
