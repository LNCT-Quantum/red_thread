"""Red Thread Progression Gate: backend-only stage and authorization decisions."""

from .authorization import (
    AuthorizationService,
    DialogueAuthorization,
    FactAuthorization,
    PreparedDialogueTurn,
)
from .evidence_reactions import (
    EvidenceReaction,
    ResolvedReaction,
    reaction_marker,
)
from .gate import ProgressionGate
from .knowledge import NpcKnowledge, load_npc_knowledge
from .progression_manager import ProgressionManager, ProgressionResult
from .progression_rules import (
    ProgressionRules,
    StageRule,
    current_stage,
    default_rules,
    load_progression_rules,
    stage_marker,
    unlocked_stage_ids,
)

__all__ = [
    "AuthorizationService",
    "DialogueAuthorization",
    "FactAuthorization",
    "PreparedDialogueTurn",
    "EvidenceReaction",
    "ResolvedReaction",
    "reaction_marker",
    "ProgressionGate",
    "NpcKnowledge",
    "load_npc_knowledge",
    "ProgressionManager",
    "ProgressionResult",
    "ProgressionRules",
    "StageRule",
    "current_stage",
    "default_rules",
    "load_progression_rules",
    "stage_marker",
    "unlocked_stage_ids",
]