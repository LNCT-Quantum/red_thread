from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.case_engine import CaseEngine

from .authorization import AuthorizationService
from .knowledge import load_npc_knowledge
from .progression_manager import ProgressionManager
from .progression_rules import ProgressionRules, load_progression_rules

__all__ = ["ProgressionGate"]


@dataclass(frozen=True, slots=True)
class ProgressionGate:
    """Convenience bundle of the manager and the authorization service."""

    manager: ProgressionManager
    authorization: AuthorizationService

    @classmethod
    def from_engine(
        cls,
        engine: CaseEngine,
        rules: ProgressionRules | None = None,
        data_root: Path | str | None = None,
    ) -> ProgressionGate:
        """Build a gate on an already-loaded Case Engine."""
        resolved = rules if rules is not None else load_progression_rules(engine, data_root)
        authorization = AuthorizationService(
            engine, resolved, load_npc_knowledge(engine, data_root)
        )
        return cls(ProgressionManager(authorization), authorization)