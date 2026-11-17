# File: backend/tests/integration/test_full_game_flow.py
import pytest
from pathlib import Path

from shared.contracts.errors import PermissionDeniedError, StateConflictError
from src.case_engine.engine import CaseEngine
from src.progression.gate import ProgressionGate
from src.game_state.state_repository import InMemoryGameStateRepository
from src.game_state.state_manager import GameStateManager

@pytest.fixture
def integration_setup():
    """
    QA Note:
    Integration Setup:
    Loads real CaseEngine, real ProgressionGate, and real StateManager.
    No Mocks are used here. 
    """
    # 1. Load the real case data (Reads case.json, clues.json, etc.)
    engine = CaseEngine.load(case_id="case_001")
    
    # 2. Build the Progression Gate (Reads progression.json and npc_knowledge.json)
    gate = ProgressionGate.from_engine(engine)
    
    # 3. Setup the In-Memory Repository and State Manager
    repository = InMemoryGameStateRepository()
    manager = GameStateManager(engine=engine, repository=repository, progression=gate)
    
    return engine, gate, manager


def test_full_investigation_flow_backend_only(integration_setup):
    """
    Test: Simulates a player playing the game from start to Stage 2.
    
    WHY NO LLM CALL HERE? 
    - We are testing the "Deterministic Backend". 
    - Calling the real LLM here would make the test slow and unpredictable.
    - The actual LLM call is tested in E2E tests (test_ttft_benchmark) and 
      Mock tests (test_mock_llm). 
    - The Full AI flow will be tested once Owner 4 integrates the FastAPI endpoints.
    """
    engine, gate, manager = integration_setup

    # --- STEP 1: Start a new game ---
    state = manager.create_game_session(game_id="game_integration_001")
    assert state.game_id == "game_integration_001"
    
    # The initial stage must be stage_1 based on progression.json
    current_stage = manager.get_current_stage_id("game_integration_001")
    assert current_stage == "stage_1"

    # --- STEP 2: Discover Clues for Stage 2 ---
    # progression.json says stage_2 requires clue_001, clue_004, and clue_012
    state_change = manager.discover_clue("game_integration_001", "clue_001")
    assert state_change.changed is True
    assert "clue_001" in state_change.state.discovered_clue_ids
    
    manager.discover_clue("game_integration_001", "clue_004")
    manager.discover_clue("game_integration_001", "clue_012")

    # --- STEP 3: Check Stage Progression ---
    # Because we discovered all required clues, the game should auto-unlock Stage 2
    current_stage = manager.get_current_stage_id("game_integration_001")
    assert current_stage == "stage_2", "Game failed to advance to stage_2 after finding all required clues."

    # --- STEP 4: Test Epistemic Security (Fact Authorization) ---
    # Prepare a dialogue turn. 
    # NOTE: This does NOT call the LLM. It only builds the DialogueRequest.
    # This ensures that before we even send data to the LLM, the backend 
    # has filtered out all unauthorized facts.
    prepared_turn = manager.prepare_dialogue_turn(
        game_id="game_integration_001",
        request_id="req_001",
        suspect_id="suspect_001",
        player_message="What do you know about this chessboard?",
        dialogue_session_id="session_001",
        presented_clue_ids=("clue_001",)
    )

    request = prepared_turn.request

    # Verify that Anaya is NOT given unauthorized facts
    # In npc_knowledge.json, fact_044 is in her unknown_fact_ids
    assert "fact_044" not in request.authorized_fact_ids
    
    # QA Note: Here we STOP. 
    # The next step would be sending `request` to the LLM, getting a Draft,
    # and validating it. This will be done in the E2E API test later.


def test_blocked_clue_discovery(integration_setup):
    """
    QA Note:
    Negative Testing: A player should NOT be able to discover a locked clue.
    For example, clue_014 (Fingerprints) is unlocked in stage_3.
    At stage_1, this should fail.
    """
    engine, gate, manager = integration_setup
    manager.create_game_session(game_id="game_negative_001")

    # Try to discover a clue that belongs to a later stage
    with pytest.raises(PermissionDeniedError, match="Clue is not unlocked yet"):
        manager.discover_clue("game_negative_001", "clue_014")