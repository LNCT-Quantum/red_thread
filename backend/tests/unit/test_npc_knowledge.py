# File: backend/tests/unit/test_npc_knowledge.py
import pytest
from src.progression.knowledge import NpcKnowledge
from src.progression.evidence_reactions import EvidenceReaction

def test_valid_npc_knowledge_creation_with_reactions():
    # Create a good reaction object
    reaction = EvidenceReaction(
        clue_id="clue_001",
        reaction_type="acknowledge",
        emotional_response="nervous"
    )
    
    # Create suspect knowledge and include the reaction
    knowledge = NpcKnowledge(
        suspect_id="suspect_001",
        known_fact_ids=("fact_001",),
        unknown_fact_ids=(),
        secret_fact_ids=(),
        evidence_reactions=(reaction,) # Tuple is correct
    )
    assert knowledge.suspect_id == "suspect_001"
    assert len(knowledge.evidence_reactions) == 1
    assert knowledge.evidence_reactions[0].clue_id == "clue_001"

def test_npc_knowledge_fails_if_reactions_is_not_a_tuple():
    # Test that 'evidence_reactions' must be a tuple
    with pytest.raises(TypeError, match="'evidence_reactions' must be a tuple"):
        NpcKnowledge(
            suspect_id="suspect_001",
            known_fact_ids=("fact_001",),
            unknown_fact_ids=(),
            secret_fact_ids=(),
            evidence_reactions=["not_a_tuple"] # List is given instead of tuple
        )

def test_npc_knowledge_fails_if_reaction_is_invalid_type():
    # Test that items inside 'evidence_reactions' must be EvidenceReaction objects
    with pytest.raises(TypeError, match="must be an EvidenceReaction"):
        NpcKnowledge(
            suspect_id="suspect_001",
            known_fact_ids=("fact_001",),
            unknown_fact_ids=(),
            secret_fact_ids=(),
            evidence_reactions=("I am just a string, not a reaction",) # Invalid type
        )