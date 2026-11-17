# File: backend/tests/unit/test_authorization.py
import pytest
from unittest.mock import MagicMock
from shared.contracts.game_state import GameState
from shared.contracts.errors import ContractValidationError
from src.progression.authorization import AuthorizationService
from src.progression.progression_rules import ProgressionRules, StageRule
from src.progression.knowledge import NpcKnowledge

@pytest.fixture
def mock_engine():
    # Create a fake Case Engine to test logic without loading real files
    engine = MagicMock()
    engine.case_id = "case_001"
    
    # Fake Case Data
    engine.case.suspect_ids = ("suspect_001",)
    engine.case.has_suspect.return_value = True
    engine.case.has_clue.return_value = True
    engine.case.has_fact.return_value = True
    engine.get_suspect.return_value = MagicMock()
    
    # Setup a clue that relates to two facts
    fake_clue = MagicMock()
    fake_clue.clue_id = "clue_001"
    fake_clue.related_fact_ids = ("fact_001", "fact_002")
    fake_clue.clue_type = "physical"
    engine.list_clues.return_value = [fake_clue]
    engine.get_clue.return_value = fake_clue
    
    # Setup the two facts
    fake_fact_1 = MagicMock()
    fake_fact_1.fact_id = "fact_001"
    fake_fact_2 = MagicMock()
    fake_fact_2.fact_id = "fact_002"
    engine.list_facts.return_value = [fake_fact_1, fake_fact_2]
    
    return engine

@pytest.fixture
def sample_rules():
    return ProgressionRules(
        case_id="case_001",
        stages=(
            StageRule(stage_id="stage_1", title="Start"),
        )
    )

@pytest.fixture
def sample_knowledge():
    # Suspect ONLY knows fact_001, they do NOT know fact_002
    return {
        "suspect_001": NpcKnowledge(
            suspect_id="suspect_001",
            known_fact_ids=("fact_001",),
            unknown_fact_ids=("fact_002",),
            secret_fact_ids=()
        )
    }

@pytest.fixture
def sample_state():
    return GameState(game_id="game_001", case_id="case_001", status="active")

def test_authorization_service_init(mock_engine, sample_rules, sample_knowledge):
    # Test that the service initializes correctly with matching case IDs
    service = AuthorizationService(mock_engine, sample_rules, sample_knowledge)
    assert service.engine == mock_engine

def test_authorization_fails_on_case_mismatch(mock_engine, sample_rules, sample_knowledge):
    # Test that it rejects if the rules are for a different case
    wrong_rules = ProgressionRules(
        case_id="case_999",
        stages=(StageRule(stage_id="stage_1", title="Start"),)
    )
    with pytest.raises(ContractValidationError, match="Progression rules belong to a different case"):
        AuthorizationService(mock_engine, wrong_rules, sample_knowledge)

def test_validate_state_rejects_wrong_case(mock_engine, sample_rules, sample_knowledge):
    # Test that it blocks a GameState from a different case
    service = AuthorizationService(mock_engine, sample_rules, sample_knowledge)
    wrong_state = GameState(game_id="game_002", case_id="case_999")
    
    with pytest.raises(ContractValidationError, match="Game state belongs to a different case"):
        service.validate_state(wrong_state)

def test_build_dialogue_request_with_no_discovered_clues(mock_engine, sample_rules, sample_knowledge, sample_state):
    # Test: If player has no clues, the suspect gets NO facts
    service = AuthorizationService(mock_engine, sample_rules, sample_knowledge)
    
    request = service.build_dialogue_request(
        state=sample_state, # State has no discovered clues
        request_id="req_001",
        suspect_id="suspect_001",
        player_message="Where were you?",
        presented_clue_ids=()
    )
    
    # Verify that the list is empty because no clues were discovered
    assert len(request.authorized_fact_ids) == 0

def test_build_dialogue_request_with_discovered_clue(mock_engine, sample_rules, sample_knowledge, sample_state):
    # Test: If player has discovered the clue, the suspect gets only the facts they know
    service = AuthorizationService(mock_engine, sample_rules, sample_knowledge)
    
    # Create a state where the player HAS discovered the clue
    state_with_clue = GameState(
        game_id="game_001", 
        case_id="case_001", 
        status="active",
        discovered_clue_ids=("clue_001",) 
    )
    
    request = service.build_dialogue_request(
        state=state_with_clue, 
        request_id="req_001",
        suspect_id="suspect_001",
        player_message="Where were you?",
        presented_clue_ids=()
    )
    
    # The clue unlocks both fact_001 and fact_002
    # But the suspect ONLY knows fact_001 (fact_002 is in unknown_fact_ids)
    assert "fact_001" in request.authorized_fact_ids
    assert "fact_002" not in request.authorized_fact_ids 
    # This proves the system correctly filters facts based on suspect knowledge.