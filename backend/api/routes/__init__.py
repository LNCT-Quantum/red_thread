"""HTTP endpoints. Handlers only validate input, call one service method and wrap the result."""

from fastapi import APIRouter

from . import cases, clues, dialogue, health, progression, sessions, suspects, timeline

__all__ = ["build_api_router"]


def build_api_router() -> APIRouter:
    router = APIRouter()
    for module in (health, cases, suspects, timeline, clues, sessions, dialogue, progression):
        router.include_router(module.router)
    return router
