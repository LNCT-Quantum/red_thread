"""Liveness and readiness."""

from __future__ import annotations

import time

from ..config import API_VERSION, SERVICE_NAME
from ..schemas.responses import ComponentStatus, HealthData, ReadyData
from .llm_gateway import LLMGateway
from .runtime import RuntimeRegistry

__all__ = ["SystemService"]


class SystemService:
    def __init__(self, registry: RuntimeRegistry, llm: LLMGateway) -> None:
        self._registry = registry
        self._llm = llm
        self._started = time.monotonic()

    def health(self) -> HealthData:
        return HealthData(
            service=SERVICE_NAME,
            version=API_VERSION,
            uptime_seconds=round(time.monotonic() - self._started, 1),
        )

    def readiness(self) -> ReadyData:
        loaded = self._registry.all()
        failed = self._registry.failed_case_ids
        components: dict[str, ComponentStatus] = {}

        if loaded and not failed:
            components["case_data"] = ComponentStatus(
                status="ok", detail=f"{len(loaded)} case(s) loaded"
            )
        elif loaded:
            components["case_data"] = ComponentStatus(
                status="unavailable",
                detail=f"{len(loaded)} case(s) loaded, {len(failed)} failed to load",
            )
        else:
            components["case_data"] = ComponentStatus(status="unavailable", detail="no case could be loaded")

        # Progression gate and state manager are built together with each case runtime.
        components["progression"] = ComponentStatus(
            status="ok" if loaded else "unavailable",
            detail=None if loaded else "no progression gate available",
        )
        components["session_store"] = ComponentStatus(
            status="ok" if loaded else "unavailable",
            detail="in-memory (sessions are lost when the backend restarts)" if loaded else None,
        )

        if not self._llm.configured:
            components["llm"] = ComponentStatus(status="unavailable", detail="not configured")
        elif self._llm.is_available():
            components["llm"] = ComponentStatus(status="ok")
        else:
            components["llm"] = ComponentStatus(status="unavailable", detail="model server unreachable")

        return ReadyData(
            ready=all(c.status == "ok" for c in components.values()), components=components
        )
