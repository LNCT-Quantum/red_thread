"""Step 1: turn a PreparedDialogueTurn into the restricted context the NPC may use."""

from __future__ import annotations

from dataclasses import dataclass

from src.case_engine import CaseEngine
from src.progression.authorization import PreparedDialogueTurn
from src.progression.evidence_reactions import ResolvedReaction
from shared.contracts.clue import Clue
from shared.contracts.fact import Fact
from shared.contracts.suspect import Suspect

MAX_HISTORY = 6  # last 6 messages is plenty for a 3B model


@dataclass(frozen=True)
class DialogueContext:
    suspect: Suspect
    facts: tuple[Fact, ...]        # only what this NPC is authorized to use
    clues: tuple[Clue, ...]        # clues the player is showing right now
    reactions: tuple[ResolvedReaction, ...]
    history: tuple[tuple[str, str], ...]   # (speaker, text)
    player_message: str
    hidden_statements: tuple[str, ...]     # facts the NPC must NOT know, for leak checks


def build_context(turn: PreparedDialogueTurn, engine: CaseEngine) -> DialogueContext:
    req = turn.request
    suspect = engine.get_suspect(req.suspect_id)

    facts = tuple(engine.get_fact(fid) for fid in req.authorized_fact_ids)
    clues = tuple(engine.get_clue(cid) for cid in req.presented_clue_ids)

    allowed = set(req.authorized_fact_ids)
    hidden = tuple(f.statement for f in engine.list_facts() if f.fact_id not in allowed)

    history = []
    for msg in req.dialogue_history[-MAX_HISTORY:]:
        speaker = "Detective" if msg.speaker_type == "player" else suspect.name
        history.append((speaker, msg.content))

    return DialogueContext(
        suspect=suspect,
        facts=facts,
        clues=clues,
        reactions=turn.reactions,
        history=tuple(history),
        player_message=req.player_message,
        hidden_statements=hidden,
    )
