# File: backend/tests/contract/test_game_state_contract.py
import pytest
from shared.contracts.game_state import GameState

def test_valid_game_state_creation():
    # Create a valid game state
    state = GameState(
        game_id="game_001",
        case_id="case_001",
        discovered_clue_ids=("clue_001", "clue_002"),
        interviewed_suspect_ids=("suspect_001",),
        completed_objective_ids=("obj_001",),
        dialogue_session_ids=("session_001",),
        current_suspect_id="suspect_001",
        status="active",
        revision=1
    )
    
    # Check if data is saved correctly
    assert state.game_id == "game_001"
    assert state.status == "active"
    assert state.revision == 1
    assert "clue_001" in state.discovered_clue_ids

def test_game_state_fails_on_empty_game_id():
    # Test that an empty game_id throws an error
    with pytest.raises(ValueError, match="must not be empty"):
        GameState(
            game_id="   ", # Empty space
            case_id="case_001"
        )

def test_game_state_fails_on_invalid_status():
    # Test that an unsupported status throws an error
    # Allowed statuses are only: active, completed, failed
    with pytest.raises(ValueError, match="must be one of"):
        GameState(
            game_id="game_002",
            case_id="case_001",
            status="paused" # 'paused' is not allowed
        )

def test_game_state_fails_on_negative_revision():
    # Test that a negative revision throws an error
    with pytest.raises(ValueError, match="must be a non-negative integer"):
        GameState(
            game_id="game_003",
            case_id="case_001",
            revision=-1 # Negative revision is invalid
        )

def test_game_state_fails_on_duplicate_clues():
    # Test that duplicate clue IDs are rejected
    with pytest.raises(ValueError, match="contains duplicate ID"):
        GameState(
            game_id="game_004",
            case_id="case_001",
            discovered_clue_ids=("clue_001", "clue_001") # Duplicate here
        )

def test_game_state_fails_on_wrong_type_for_clues():
    # Test that a list instead of tuple throws a TypeError
    with pytest.raises(TypeError, match="must be a tuple"):
        GameState(
            game_id="game_005",
            case_id="case_001",
            discovered_clue_ids=["clue_001"] # List is invalid, needs tuple
        )