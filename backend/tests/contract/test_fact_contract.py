# File: backend/tests/contract/test_fact_contract.py
import pytest
from shared.contracts.fact import Fact

def test_valid_fact_creation():
    # Create a valid fact
    fact = Fact(
        fact_id="fact_001",
        case_id="case_001",
        statement="Victim was alive at 9 PM.",
        category="Timeline",
        importance="High",
        related_entity_ids=("victim_001", "suspect_001")
    )
    
    # Check if data is correct
    assert fact.statement == "Victim was alive at 9 PM."
    assert "victim_001" in fact.related_entity_ids

def test_fact_fails_on_empty_statement():
    # Test that an empty statement throws an error
    with pytest.raises(ValueError, match="must not be empty"):
        Fact(
            fact_id="fact_002",
            case_id="case_001",
            statement="", # Empty string
            category="Timeline",
            importance="High"
        )

def test_fact_fails_on_duplicate_entity_ids():
    # Test that duplicate entity IDs are rejected
    with pytest.raises(ValueError, match="contains duplicate ID"):
        Fact(
            fact_id="fact_003",
            case_id="case_001",
            statement="Suspect was present.",
            category="Evidence",
            importance="Medium",
            related_entity_ids=("suspect_001", "suspect_001") # Duplicate here
        )

def test_fact_fails_on_wrong_type_for_entity_ids():
    # Test that a list instead of tuple throws a TypeError
    with pytest.raises(TypeError, match="must be a tuple"):
        Fact(
            fact_id="fact_004",
            case_id="case_001",
            statement="Suspect was present.",
            category="Evidence",
            importance="Medium",
            related_entity_ids=["suspect_001"] # List is invalid, needs tuple
        )