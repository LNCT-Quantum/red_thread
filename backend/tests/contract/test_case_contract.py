import pytest
from backend.shared.contracts.case import Case

def test_valid_case_creation():
    # Correct case data
    valid_case = Case(
        case_id="case_001",
        title="The Silent Witness",
        description="A doctor is dead.",
        victim_id="victim_001",
        suspect_ids=("suspect_001", "suspect_002", "suspect_003"),
        fact_ids=("fact_001", "fact_002"),
        clue_ids=("clue_001",),
        timeline_event_ids=("event_001",)
    )
    # Verify 
    assert valid_case.has_suspect("suspect_001") is True
    assert valid_case.has_suspect("suspect_999") is False

def test_case_fails_on_empty_title():
    # 2. Test: if empty title, then  TypeError/ValueError 
    with pytest.raises(ValueError, match="must not be empty"):
        Case(
            case_id="case_001",
            title="   ", #  space
            description="A doctor is dead.",
            victim_id="victim_001",
            suspect_ids=("suspect_001",),
            fact_ids=("fact_001",),
            clue_ids=("clue_001",),
            timeline_event_ids=("event_001",)
        )

def test_case_fails_on_duplicate_suspect_ids():
    # 3. Test: if  same ID two times aaye, then error
    with pytest.raises(ValueError, match="duplicate ID"):
        Case(
            case_id="case_001",
            title="The Silent Witness",
            description="A doctor is dead.",
            victim_id="victim_001",
            suspect_ids=("suspect_001", "suspect_001"), # Duplicate
            fact_ids=("fact_001",),
            clue_ids=("clue_001",),
            timeline_event_ids=("event_001",)
        )