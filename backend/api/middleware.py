"""Request IDs, body-size guard, safe access logging and the last-resort 500 handler."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .envelope import failure

__all__ = ["RequestContextMiddleware", "REQUEST_ID_HEADER"]

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{7,127}$")

log = logging.getLogger("redthread.api.access")


def resolve_request_id(supplied: str | None) -> str:
    """Reuse a well-formed client ``X-Request-ID`` (for tracing), otherwise mint one."""
    if supplied and _SAFE_REQUEST_ID.match(supplied):
        return supplied
    return f"req_{uuid.uuid4().hex}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started = time.perf_counter()

        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_body_bytes:
            response = failure(
                request_id, 413, "PAYLOAD_TOO_LARGE", "The request body is too large"
            )
        else:
            try:
                response = await call_next(request)
            except Exception:  # noqa: BLE001 - last resort; details stay in the server log
                log.exception("unhandled error request_id=%s %s %s", request_id, request.method, request.url.path)
                response = failure(
                    request_id, 500, "INTERNAL_ERROR", "An unexpected error occurred"
                )

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Log method, path and status only: never bodies, query strings or headers.
        log.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
