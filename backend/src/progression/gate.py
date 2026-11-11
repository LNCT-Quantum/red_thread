from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.case_engine import CaseEngine

from .authorization import AuthorizationService
from .knowledge import NpcKnowledge, load_npc_knowledge
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
        knowledge: Mapping[str, NpcKnowledge] | None = None,
    ) -> ProgressionGate:
        """Build a gate on an already-loaded Case Engine.

        ``rules`` and ``knowledge`` default to the case's own files; passing them
        explicitly is meant for tests and tooling.
        """
        resolved = rules if rules is not None else load_progression_rules(engine, data_root)
        resolved_knowledge = (
            knowledge if knowledge is not None else load_npc_knowledge(engine, data_root)
        )
        authorization = AuthorizationService(engine, resolved, resolved_knowledge)
        return cls(ProgressionManager(authorization), authorization)