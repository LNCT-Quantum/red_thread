# File: backend/tests/contract/test_clue_contract.py
import pytest
from shared.contracts.clue import Clue

def test_valid_clue_creation():
    # Create a valid clue
    clue = Clue(
        clue_id="clue_001",
        case_id="case_001",
        title="Bloodstain",
        description="Blood on the carpet.",
        clue_type="Physical",
        source="Crime Scene",
        related_fact_ids=("fact_001", "fact_002"),
        reliability=0.9
    )
    
    # Check if data is correct
    assert clue.title == "Bloodstain"
    assert clue.reliability == 0.9

def test_clue_fails_on_invalid_reliability():
    # Test that reliability above 1.0 throws an error
    with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
        Clue(
            clue_id="clue_002",
            case_id="case_001",
            title="Fingerprints",
            description="Fingerprints on glass.",
            clue_type="Forensic",
            source="Lab",
            reliability=1.5 # Invalid (greater than 1.0)
        )

def test_clue_fails_on_duplicate_fact_ids():
    # Test that duplicate fact IDs are rejected
    with pytest.raises(ValueError, match="contains duplicate ID"):
        Clue(
            clue_id="clue_003",
            case_id="case_001",
            title="Weapon",
            description="A knife.",
            clue_type="Physical",
            source="Kitchen",
            related_fact_ids=("fact_003", "fact_003") # Duplicate here
        )

def test_clue_fails_on_empty_title():
    # Test that an empty title throws an error
    with pytest.raises(ValueError, match="must not be empty"):
        Clue(
            clue_id="clue_004",
            case_id="case_001",
            title="   ", # Empty space
            description="Some description",
            clue_type="Physical",
            source="Unknown"
        )