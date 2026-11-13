# File: backend/tests/unit/test_validation.py
#NOTE: we will use fake case data here
import pytest
from src.case_engine.validation import validate_case_data
from src.case_engine.loader import CaseData
from src.case_engine.timeline import TimelineEvent
from shared.contracts.case import Case
from shared.contracts.fact import Fact
from shared.contracts.clue import Clue
from shared.contracts.suspect import Suspect # <-- Import Suspect here

@pytest.fixture
def base_valid_case_data():
    """
    QA Note: 
    We create a 100% valid CaseData fixture first. 
    The validator checks for EMPTY_COLLECTIONS (e.g., no suspects, no events).
    Therefore, we must provide at least one valid object of every type.
    """
    # 1. Create a valid Suspect (Required to avoid EMPTY_COLLECTION for suspects)
    suspect = Suspect(
        suspect_id="suspect_001",
        name="Test Suspect",
        occupation="Tester",
        background="Testing background",
        public_description="Testing description",
        relationship_to_victim="None",
        speech_style="Normal"
    )
    
    # 2. Create a valid event (Required to avoid EMPTY_COLLECTION for events)
    event = TimelineEvent(
        timeline_event_id="event_001",
        case_id="case_001",
        timestamp="Day 1 [approximate]",
        event_description="A dummy event for valid setup.",
        involved_entity_ids=("suspect_001",), # Linked to suspect to be safe
        related_fact_ids=("fact_001",)
    )
    
    # 3. Create the Case
    case = Case(
        case_id="case_001", 
        title="Test Case", 
        description="Test Description", 
        victim_id="victim_001", 
        suspect_ids=("suspect_001",), 
        fact_ids=("fact_001",), 
        clue_ids=("clue_001",), 
        timeline_event_ids=("event_001",)
    )
    
    # 4. Create valid Fact and Clue
    fact = Fact(fact_id="fact_001", case_id="case_001", statement="Valid Fact", category="Test", importance="High")
    clue = Clue(
        clue_id="clue_001", 
        case_id="case_001", 
        title="Valid Clue", 
        description="Valid Desc", 
        clue_type="physical", 
        source="Test", 
        related_fact_ids=("fact_001",)
    )
    
    return CaseData(
        case=case, 
        suspects=(suspect,), # <-- Added Suspect to avoid EMPTY_COLLECTION
        facts=(fact,), 
        clues=(clue,), 
        timeline_events=(event,)
    )


def test_validation_passes_on_good_data(base_valid_case_data):
    """
    Test: The validator should return zero errors for a 100% valid case.
    """
    report = validate_case_data(base_valid_case_data)
    
    # If this fails, it will print the exact error codes
    assert report.is_valid is True, f"Unexpected errors: {[i.code for i in report.errors]}"


def test_validation_fails_on_missing_fact_reference(base_valid_case_data):
    """
    Test: If a clue references a fact that doesn't exist, the validator MUST catch it.
    """
    # Create a broken clue
    broken_clue = Clue(
        clue_id="clue_002", 
        case_id="case_001", 
        title="Broken Clue", 
        description="Refers to a missing fact", 
        clue_type="physical", 
        source="Test", 
        related_fact_ids=("fact_999",) # ERROR INJECTED HERE
    )
    
    broken_data = CaseData(
        case=base_valid_case_data.case,
        suspects=base_valid_case_data.suspects,
        facts=base_valid_case_data.facts,
        clues=(broken_clue,), 
        timeline_events=base_valid_case_data.timeline_events
    )
    
    report = validate_case_data(broken_data)
    
    assert report.is_valid is False
    assert any("UNKNOWN_FACT_REFERENCE" in issue.code for issue in report.errors)