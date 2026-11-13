# File: backend/tests/unit/test_engine.py
import pytest
from unittest.mock import MagicMock
from shared.contracts.errors import PermissionDeniedError, ResourceNotFoundError
from src.case_engine.engine import CaseEngine, _State, CaseRegistry

@pytest.fixture
def mock_engine():
    # Create a minimal fake state to test the Engine without loading real files
    fake_case = MagicMock()
    fake_case.case_id = "case_001"
    fake_case.victim_id = "victim_1"
    
    fake_registry = CaseRegistry(
        case=fake_case, suspects=(), facts=(), clues=(), timeline_events=(), entity_references=()
    )
    
    # We need empty mappings for the engine's internal state
    fake_state = _State(
        registry=fake_registry, report=MagicMock(), assumptions=(),
        suspects={"suspect_1": MagicMock()}, facts={"fact_1": MagicMock()},
        clues={"clue_1": MagicMock()}, events={}, entities={}, descriptors={},
        clues_by_fact={"fact_1": ()}, facts_by_clue={"clue_1": ()},
        events_by_fact={}, facts_by_event={}, facts_by_entity={},
        events_by_entity={}, clues_by_source={}, assumption_edges={}
    )
    
    return CaseEngine(fake_state)

def test_engine_is_read_only(mock_engine):
    # Test that we cannot modify the engine after it is created
    with pytest.raises(PermissionDeniedError, match="CaseEngine is read-only"):
        mock_engine.case_id = "hacked"
        
    with pytest.raises(PermissionDeniedError, match="CaseEngine is read-only"):
        del mock_engine.case_id

def test_get_suspect_success(mock_engine):
    # Test getting a valid suspect
    suspect = mock_engine.get_suspect("suspect_1")
    assert suspect is not None

def test_get_suspect_not_found(mock_engine):
    # Test that getting an invalid suspect throws an error
    with pytest.raises(ResourceNotFoundError, match="Unknown suspect id"):
        mock_engine.get_suspect("suspect_999")

def test_get_fact_not_found(mock_engine):
    # Test that getting an invalid fact throws an error
    with pytest.raises(ResourceNotFoundError, match="Unknown fact id"):
        mock_engine.get_fact("fact_999")

def test_relationships(mock_engine):
    # Test that the engine correctly fetches related data
    # (e.g., getting facts for a clue)
    facts = mock_engine.facts_for_clue("clue_1")
    assert isinstance(facts, tuple)