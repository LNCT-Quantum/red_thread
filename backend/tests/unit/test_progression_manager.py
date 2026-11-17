# File: backend/tests/unit/test_progression_manager.py
import pytest
from unittest.mock import MagicMock
from shared.contracts.game_state import GameState
from shared.contracts.errors import PermissionDeniedError
from src.progression.progression_manager import ProgressionManager
from src.progression.progression_rules import ProgressionRules, StageRule

@pytest.fixture
def mock_authorization():
    # Create a fake Authorization Service
    auth = MagicMock()
    
    # GIVE IT 3 STAGES SO WE CAN TEST SKIPPING (Stage 1 -> Stage 3)
    rules = ProgressionRules(
        case_id="case_001",
        stages=(
            StageRule(stage_id="stage_1", title="Start"),
            StageRule(stage_id="stage_2", title="Mid", required_clue_ids=("clue_001",)),
            StageRule(stage_id="stage_3", title="End", required_clue_ids=("clue_002",))
        )
    )
    auth.rules = rules
    auth.engine.case_id = "case_001"
    return auth

@pytest.fixture
def sample_game_state():
    # Create a basic active game state
    return GameState(game_id="game_001", case_id="case_001", status="active", revision=1)

def test_progression_manager_record_interview(mock_authorization, sample_game_state):
    # Test that recording an interview updates the game state
    manager = ProgressionManager(mock_authorization)
    mock_authorization.engine.get_suspect.return_value = True
    new_state = manager.record_interview(sample_game_state, "suspect_001")
    assert "suspect_001" in new_state.interviewed_suspect_ids
    assert new_state.revision == 2

def test_progression_manager_denies_stage_skip(mock_authorization, sample_game_state):
    # Test that a player cannot jump directly from stage 1 to stage 3
    manager = ProgressionManager(mock_authorization)
    
    # Try to unlock stage 3 (skipping stage 2)
    with pytest.raises(PermissionDeniedError, match="Stages cannot be skipped"):
        manager.unlock_stage(sample_game_state, "stage_3")

def test_progression_manager_denies_if_requirements_unmet(mock_authorization, sample_game_state):
    # Test that the player is blocked if they don't have the required clue
    manager = ProgressionManager(mock_authorization)
    
    # Try to unlock stage 2 (which requires clue_001, but player has none)
    with pytest.raises(PermissionDeniedError, match="Stage requirements are not met"):
        manager.unlock_stage(sample_game_state, "stage_2")

def test_progression_manager_fails_if_game_not_active(mock_authorization):
    # Test that no actions are allowed if the game is finished
    manager = ProgressionManager(mock_authorization)
    dead_state = GameState(game_id="game_001", case_id="case_001", status="completed")
    with pytest.raises(Exception, match="Game is not active"):
        manager.record_interview(dead_state, "suspect_001")