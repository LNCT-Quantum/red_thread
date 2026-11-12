# File: backend/tests/unit/test_state_repository.py
import pytest
from shared.contracts.game_state import GameState
from shared.contracts.dialogue import DialogueMessage
from shared.contracts.errors import StateConflictError, ResourceNotFoundError, ContractValidationError
from src.game_state.state_repository import GameSession, InMemoryGameStateRepository
from datetime import datetime, timezone

@pytest.fixture
def repo():
    return InMemoryGameStateRepository()

@pytest.fixture
def sample_state():
    return GameState(game_id="game_1", case_id="case_001", status="active", revision=0)

@pytest.fixture
def sample_message():
    return DialogueMessage(
        message_id="msg_1", session_id="sess_1", case_id="case_001",
        speaker_type="player", speaker_id=None, content="Hello",
        sequence_number=1, created_at=datetime.now(timezone.utc)
    )

def test_create_and_get_session(repo, sample_state):
    # Test saving and retrieving a session
    session = GameSession(state=sample_state)
    repo.create(session)
    
    retrieved = repo.get("game_1")
    assert retrieved.state.game_id == "game_1"

def test_create_duplicate_session_fails(repo, sample_state):
    # Test that creating a session with an existing ID throws an error
    repo.create(GameSession(state=sample_state))
    
    with pytest.raises(StateConflictError, match="already exists"):
        repo.create(GameSession(state=sample_state))

def test_get_unknown_session_fails(repo):
    # Test that getting an unknown ID throws an error
    with pytest.raises(ResourceNotFoundError, match="Unknown game session"):
        repo.get("unknown_id")

def test_save_optimistic_locking(repo, sample_state, sample_message):
    # Test that saving with the wrong revision fails
    repo.create(GameSession(state=sample_state))
    
    # Create a new state with revision 1
    new_state = GameState(game_id="game_1", case_id="case_001", revision=1)
    new_session = GameSession(state=new_state, dialogue_history=(sample_message,))
    
    # Try to save with expected_revision=0 (valid)
    repo.save(new_session, expected_revision=0)
    
    # Try to save again with expected_revision=0 (stale, actual is 1)
    with pytest.raises(StateConflictError, match="modified concurrently"):
        repo.save(new_session, expected_revision=0)

def test_save_must_advance_revision(repo, sample_state):
    # Test that a save must increase revision by exactly 1
    repo.create(GameSession(state=sample_state))
    
    # Try to save with same revision (0)
    with pytest.raises(ContractValidationError, match="must advance the revision by exactly one"):
        repo.save(GameSession(state=sample_state), expected_revision=0)

def test_dialogue_history_is_append_only(repo, sample_state, sample_message):
    # Test that old messages cannot be deleted or rewritten
    repo.create(GameSession(state=sample_state, dialogue_history=(sample_message,)))
    
    # Create a new state with revision 1 but EMPTY history
    new_state = GameState(game_id="game_1", case_id="case_001", revision=1)
    bad_session = GameSession(state=new_state, dialogue_history=())
    
    with pytest.raises(ContractValidationError, match="append-only"):
        repo.save(bad_session, expected_revision=0)