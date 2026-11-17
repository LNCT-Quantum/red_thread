# File: backend/tests/unit/dialogue_generator/test_context_builder.py
import pytest
from unittest.mock import MagicMock
from src.dialogue_generator.context_builder import build_context
from src.progression.authorization import PreparedDialogueTurn
from shared.contracts.dialogue import DialogueRequest

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.get_suspect.return_value = MagicMock(name="Anaya")
    engine.get_fact.side_effect = lambda fid: MagicMock(fact_id=fid, statement=f"Statement of {fid}")
    engine.get_clue.side_effect = lambda cid: MagicMock(clue_id=cid)
    
    # Mocking all case facts (fact_001 is allowed, fact_002 is hidden)
    engine.list_facts.return_value = [
        MagicMock(fact_id="fact_001", statement="I am allowed to say this."),
        MagicMock(fact_id="fact_002", statement="I must hide this secret.")
    ]
    return engine

@pytest.fixture
def mock_turn():
    # A turn where only fact_001 is authorized
    request = DialogueRequest(
        request_id="req_1", case_id="case_001", suspect_id="suspect_001",
        player_message="Where were you?", authorized_fact_ids=("fact_001",),
        presented_clue_ids=("clue_001",)
    )
    return PreparedDialogueTurn(request=request, reactions=())

def test_context_builder_filters_authorized_and_hidden_facts(mock_engine, mock_turn):
    ctx = build_context(mock_turn, mock_engine)
    
    # Verify that only authorized facts are in the context
    assert len(ctx.facts) == 1
    assert ctx.facts[0].fact_id == "fact_001"
    
    # Verify that hidden facts are captured for leak detection
    assert len(ctx.hidden_statements) == 1
    assert "I must hide this secret." in ctx.hidden_statements