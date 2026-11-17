# File: backend/tests/contract/test_suspect_contract.py
import pytest
from shared.contracts.suspect import Suspect

def test_valid_suspect_creation():
    # Create a valid suspect with correct data
    suspect = Suspect(
        suspect_id="suspect_001",
        name="Anaya",
        occupation="Psychologist",
        background="She knew the victim.",
        public_description="A calm woman.",
        relationship_to_victim="Friend",
        speech_style="Soft spoken",
        age=30,
        personality_traits=("calm", "observant")
    )
    
    # Check if data is saved correctly
    assert suspect.name == "Anaya"
    assert suspect.age == 30
    assert "calm" in suspect.personality_traits

def test_suspect_fails_on_empty_name():
    # Test that an empty name throws an error
    with pytest.raises(ValueError, match="must not be empty"):
        Suspect(
            suspect_id="suspect_002",
            name="   ", # Empty space
            occupation="Doctor",
            background="Some background",
            public_description="Some description",
            relationship_to_victim="Stranger",
            speech_style="Loud"
        )

def test_suspect_fails_on_invalid_age():
    # Test that a negative age throws an error
    with pytest.raises(ValueError, match="must be a positive integer"):
        Suspect(
            suspect_id="suspect_003",
            name="Kabir",
            occupation="Businessman",
            background="Some background",
            public_description="Some description",
            relationship_to_victim="Business partner",
            speech_style="Formal",
            age=-5 # Negative age is invalid
        )

def test_suspect_fails_on_duplicate_traits():
    # Test that duplicate traits are rejected
    with pytest.raises(ValueError, match="contains duplicate trait"):
        Suspect(
            suspect_id="suspect_004",
            name="Nisha",
            occupation="Researcher",
            background="Some background",
            public_description="Some description",
            relationship_to_victim="Colleague",
            speech_style="Nervous",
            personality_traits=("nervous", "nervous") # Duplicate here
        )