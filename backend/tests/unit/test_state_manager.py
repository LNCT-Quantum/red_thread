# File: backend/tests/unit/test_state_manager.py
#NOTE: We use MagicMock for the Repository and Engine because this is a Unit test.
#We want to test the Manager's logic, not the database
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from shared.contracts.game_state import GameState
from shared.contracts.dialogue import DialogueMessage
from shared.contracts.errors import ContractValidationError, StateConflictError
from src.game_state.state_manager import GameStateManager
from src.game_state.state_repository import GameSession

@pytest.fixture
def mock_engine():
    # Create a fake Case Engine
    engine = MagicMock()
    engine.case_id = "case_001"
    return engine

@pytest.fixture
def mock_repository():
    # Create a fake Repository that stores sessions in memory
    repo = MagicMock()
    _storage = {}
    
    def mock_create(session):
        _storage[session.state.game_id] = session
        
    def mock_get(game_id):
        if game_id not in _storage:
            raise Exception("Not found")
        return _storage[game_id]
        
    def mock_save(session, expected_rev):
        # Check optimistic locking
        current = _storage[session.state.game_id]
        if current.revision != expected_rev:
            raise StateConflictError("Revision mismatch")
        _storage[session.state.game_id] = session

    repo.create.side_effect = mock_create
    repo.get.side_effect = mock_get
    repo.save.side_effect = mock_save
    return repo

@pytest.fixture
def state_manager(mock_engine, mock_repository):
    return GameStateManager(engine=mock_engine, repository=mock_repository)

@pytest.fixture
def sample_message():
    return DialogueMessage(
        message_id="msg_1",
        session_id="sess_1",
        case_id="case_001",
        speaker_type="player",
        speaker_id=None,
        content="Hello",
        sequence_number=1,
        created_at=datetime.now(timezone.utc)
    )

def test_create_game_session(state_manager):
    # Test creating a new game session
    state = state_manager.create_game_session(game_id="game_123")
    assert state.game_id == "game_123"
    assert state.revision == 0
    assert state.status == "active"

def test_append_dialogue_message(state_manager, sample_message):
    # Test appending a valid message to the session
    state_manager.create_game_session(game_id="game_123")
    
    change = state_manager.append_dialogue_message("game_123", sample_message)
    
    assert change.changed is True
    # Revision should increase
    assert change.state.revision == 1
    # Session ID should be recorded
    assert "sess_1" in change.state.dialogue_session_ids

def test_append_duplicate_message_fails(state_manager, sample_message):
    # Test that sending the same message ID again throws an error
    state_manager.create_game_session(game_id="game_123")
    state_manager.append_dialogue_message("game_123", sample_message)
    
    # Try to append a DIFFERENT message with the SAME id
    bad_msg = DialogueMessage(
        message_id="msg_1", # Same ID
        session_id="sess_1",
        case_id="case_001",
        speaker_type="player",
        speaker_id=None,
        content="Different content",
        sequence_number=2,
        created_at=datetime.now(timezone.utc)
    )
    
    with pytest.raises(StateConflictError, match="A different message with this ID already exists"):
        state_manager.append_dialogue_message("game_123", bad_msg)

def test_discover_clue(state_manager):
    # Test discovering a valid clue
    state_manager.create_game_session(game_id="game_123")
    
    change = state_manager.discover_clue("game_123", "clue_999")
    
    assert change.changed is True
    assert "clue_999" in change.state.discovered_clue_ids
    assert change.state.revision == 1

def test_optimistic_locking_fails(state_manager, sample_message):
    # Test that if a stale revision is passed, the save fails
    state_manager.create_game_session(game_id="game_123")
    
    # Pass expected_revision=5 when actual is 0
    with pytest.raises(StateConflictError, match="Game session was modified concurrently"):
        state_manager.append_dialogue_message("game_123", sample_message, expected_revision=5)