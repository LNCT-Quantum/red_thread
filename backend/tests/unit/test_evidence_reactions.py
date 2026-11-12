# File: backend/tests/unit/test_evidence_reactions.py
import pytest
from src.progression.evidence_reactions import EvidenceReaction

def test_valid_evidence_reaction_creation():
    # Create a good reaction where suspect reveals a fact
    reaction = EvidenceReaction(
        clue_id="clue_001",
        reaction_type="acknowledge",
        emotional_response="nervous",
        reveals_fact_ids=("fact_001",),
        conceals_fact_ids=("fact_002",)
    )
    assert reaction.clue_id == "clue_001"
    assert "fact_001" in reaction.reveals_fact_ids

def test_reaction_fails_on_invalid_type():
    # Test that an unknown reaction type is rejected
    with pytest.raises(ValueError, match="'reaction_type' must be one of"):
        EvidenceReaction(
            clue_id="clue_001",
            reaction_type="angry", # Not in the allowed list
            emotional_response="mad"
        )

def test_reaction_fails_if_fact_both_revealed_and_concealed():
    # Test that a fact cannot be in both lists
    with pytest.raises(ValueError, match="facts cannot be both revealed and concealed"):
        EvidenceReaction(
            clue_id="clue_001",
            reaction_type="acknowledge",
            emotional_response="nervous",
            reveals_fact_ids=("fact_001",),
            conceals_fact_ids=("fact_001",) # Overlap here
        )

def test_no_recognition_cannot_reveal_facts():
    # Test that if suspect has no recognition, they cannot reveal facts
    with pytest.raises(ValueError, match="a 'no_recognition' reaction must not reveal or conceal facts"):
        EvidenceReaction(
            clue_id="clue_001",
            reaction_type="no_recognition",
            emotional_response="confused",
            reveals_fact_ids=("fact_001",) # Illegal for this type
        )