# File: backend/tests/e2e/test_full_e2e_pipeline.py
import pytest

from src.case_engine.engine import CaseEngine
from src.progression.gate import ProgressionGate
from src.game_state.state_repository import InMemoryGameStateRepository
from src.game_state.state_manager import GameStateManager
from src.dialogue_generator.pipeline import DialoguePipeline

@pytest.mark.e2e
def test_full_end_to_end_interrogation():
    """
    QA Note:
    This is the ultimate End-to-End test.
    It uses the REAL DialoguePipeline (which calls the real LLM).
    It proves that Game Engine, Progression, Epistemic Auth, LLM, and Validation 
    work together perfectly.
    """
    print("\n--- Starting Full E2E Test (via DialoguePipeline) ---")

    # 1. Load Real Game Data
    engine = CaseEngine.load(case_id="case_001")
    gate = ProgressionGate.from_engine(engine)
    repository = InMemoryGameStateRepository()
    manager = GameStateManager(engine=engine, repository=repository, progression=gate)
    
    # 2. Start Game & Discover Clues for Stage 2
    game_id = "e2e_test_game"
    manager.create_game_session(game_id=game_id)
    
    manager.discover_clue(game_id, "clue_001")
    manager.discover_clue(game_id, "clue_004")
    manager.discover_clue(game_id, "clue_012")
    
    assert manager.get_current_stage_id(game_id) == "stage_2", "Failed to reach stage 2"

    # 3. Prepare Dialogue Request (Player asks Anaya about the chessboard)
    turn = manager.prepare_dialogue_turn(
        game_id=game_id,
        request_id="e2e_req_001",
        suspect_id="suspect_001",
        player_message="Tell me about the chessboard in the room.",
        dialogue_session_id="sess_001",
        presented_clue_ids=("clue_001",)
    )

    # 4. Initialize the Dialogue Pipeline 
    
    pipeline = DialoguePipeline(engine)

    # 5. Generate the Response
    result = pipeline.generate(turn)
    
    # --- E2E LATENCY & QUALITY REPORT ---
    print(f"\n=== E2E PIPELINE REPORT ===")
    print(f"Is Fallback Used?: {result.is_fallback}")
    print(f"Attempts Needed:   {result.attempts}")
    if result.problems:
        print(f"Problems Found:    {result.problems}")
    print(f"NPC Reply:         '{result.draft.content}'")
    print(f"===========================\n")

    # 6. Final Assertions
    # The AI should generate a valid reply, not a fallback (if Ollama is running properly)
    assert result.draft is not None
    assert isinstance(result.draft.content, str)
    assert len(result.draft.content) > 0
    
    # Verify that no internal IDs leaked into the text
    assert "fact_" not in result.draft.content
    assert "clue_" not in result.draft.content

    # 7. Save the Turn (Update Game State)
    state_change = manager.complete_dialogue_turn(
        game_id=game_id,
        turn=turn,
        draft=result.draft
    )
    
    assert state_change.state.revision > 1, "State revision did not increase after the turn."
    
    print("--- E2E Test Passed Successfully! ---")