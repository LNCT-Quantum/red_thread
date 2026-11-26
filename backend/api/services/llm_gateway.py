"""Thin holder for the one shared local LLM engine so it can be health-checked and faked in tests.

The same engine instance is handed to ``InterrogationService`` (see ``DialogueService``), so
only one Ollama client exists per app.
"""

from __future__ import annotations

import logging
from typing import Any

from src.llm.engine_runner import EngineError, LocalLLMEngine

__all__ = ["LLMGateway"]

log = logging.getLogger("redthread.api.llm")


class LLMGateway:
    """Wraps a ``LocalLLMEngine`` (or any object with its ``check_health``/``stream_generate``).

    Constructing the engine does not contact the model server, so the API starts even when
    Ollama is down; the problem then shows up in ``/health/ready`` and as 503 on dialogue.
    """

    def __init__(self, engine: Any | None, error: str | None = None) -> None:
        self._engine = engine
        self.error = error

    @classmethod
    def from_environment(cls) -> LLMGateway:
        try:
            return cls(LocalLLMEngine())
        except EngineError as exc:
            log.error("LLM engine is not configured correctly: %s", exc)
            return cls(None, error="LLM engine configuration is invalid")

    @property
    def configured(self) -> bool:
        return self._engine is not None

    def is_available(self) -> bool:
        """True when the model server answers its health probe (bounded by the connect timeout)."""
        if self._engine is None:
            return False
        try:
            return bool(self._engine.check_health())
        except Exception:  # noqa: BLE001 - a failing probe simply means "not available"
            log.warning("LLM health probe raised", exc_info=True)
            return False

    @property
    def engine(self) -> Any | None:
        """The shared engine (``None`` when the configuration was invalid)."""
        return self._engine
