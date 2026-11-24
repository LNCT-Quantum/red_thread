"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import API_PREFIX, API_VERSION, Settings
from .dependencies import AppContainer, build_container
from .errors import register_exception_handlers
from .middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from .routes import build_api_router

__all__ = ["create_app"]

_DESCRIPTION = """
REST API for **Red Thread - AI Detective Game**.

Every response uses one envelope: `request_id`, `success`, `data`, `error`, `schema_version`.
Sessions live in memory and are lost when the backend restarts. See `backend/docs/api_documentation.md`.
"""


def create_app(
    settings: Settings | None = None,
    *,
    llm_engine: Any | None = None,
    container: AppContainer | None = None,
) -> FastAPI:
    """Build the app. ``llm_engine`` / ``container`` exist so tests never need a real LLM."""
    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    container = container or build_container(settings, llm_engine=llm_engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        container.close()

    docs = settings.enable_docs
    app = FastAPI(
        title="Red Thread API",
        version=API_VERSION,
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    )
    app.state.container = container

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware, max_body_bytes=settings.max_body_bytes)
    if settings.cors_origins:  # added last so it is the outermost layer (covers error responses too)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", REQUEST_ID_HEADER],
            expose_headers=[REQUEST_ID_HEADER],
        )
    app.include_router(build_api_router(), prefix=API_PREFIX)
    return app
