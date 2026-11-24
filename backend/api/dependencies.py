"""Application container and FastAPI dependencies.

The container is created once per app, stored on ``app.state`` and injected into routes.
Nothing is a module-level global, so every test (and every app instance) is isolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request

from .config import Settings
from .services.case_service import CaseService
from .services.dialogue_service import DialogueService
from .services.game_service import GameService
from .services.guards import SessionGuards
from .services.llm_gateway import LLMGateway
from .services.runtime import RuntimeRegistry
from .services.system_service import SystemService

__all__ = [
    "AppContainer", "build_container", "get_request_id", "RequestId",
    "CaseSvc", "GameSvc", "DialogueSvc", "SystemSvc",
]


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    registry: RuntimeRegistry
    llm: LLMGateway
    guards: SessionGuards
    system: SystemService
    cases: CaseService
    games: GameService
    dialogue: DialogueService

    def close(self) -> None:
        self.dialogue.close()


def build_container(
    settings: Settings,
    llm_engine: Any | None = None,
    registry: RuntimeRegistry | None = None,
) -> AppContainer:
    """Wire the services. ``llm_engine`` lets tests supply a scripted engine (no real LLM)."""
    registry = registry or RuntimeRegistry.load(settings.case_ids, settings.case_data_root)
    llm = LLMGateway(llm_engine) if llm_engine is not None else LLMGateway.from_environment()
    guards = SessionGuards()
    return AppContainer(
        settings=settings,
        registry=registry,
        llm=llm,
        guards=guards,
        system=SystemService(registry, llm),
        cases=CaseService(registry),
        games=GameService(registry, guards, settings.interview_min_turns),
        dialogue=DialogueService(
            registry, guards, llm, settings.dialogue_timeout_s, settings.llm_concurrency
        ),
    )


def _container(request: Request) -> AppContainer:
    return request.app.state.container


def get_request_id(request: Request) -> str:
    return request.state.request_id


def _cases(request: Request) -> CaseService:
    return _container(request).cases


def _games(request: Request) -> GameService:
    return _container(request).games


def _dialogue(request: Request) -> DialogueService:
    return _container(request).dialogue


def _system(request: Request) -> SystemService:
    return _container(request).system


RequestId = Annotated[str, Depends(get_request_id)]
CaseSvc = Annotated[CaseService, Depends(_cases)]
GameSvc = Annotated[GameService, Depends(_games)]
DialogueSvc = Annotated[DialogueService, Depends(_dialogue)]
SystemSvc = Annotated[SystemService, Depends(_system)]
