"""Red Thread REST API layer (FastAPI).

The API is a thin integration layer: routes handle HTTP, services coordinate the
existing backend modules (``CaseEngine``, ``GameStateManager``, ``ProgressionGate``,
``DialoguePipeline``) and schemas define the only data shapes the frontend ever sees.
"""

from .config import API_PREFIX, API_VERSION, Settings

__all__ = ["API_PREFIX", "API_VERSION", "Settings"]
