# File: backend/tests/unit/test_dialogue_pipeline.py
import pytest
from unittest.mock import MagicMock
from src.dialogue_generator.pipeline import DialoguePipeline
from src.dialogue_generator.llm_adapter import LLMError, LLMResult

@pytest.fixture
def mock_pipeline_setup():
    engine = MagicMock()
    adapter = MagicMock()
    pipeline = DialoguePipeline(engine, adapter=adapter)
    
    # Mock the internal extractor and context builder
    pipeline.extractor = MagicMock()
    pipeline.extractor.extract.return_value.draft = MagicMock(
        content="Valid reply", cited_fact_ids=(), cited_clue_ids=()
    )
    pipeline.build_context = MagicMock(return_value=MagicMock(hidden_statements=()))
    
    # FIX: Set real string values for the turn's request attributes
    turn = MagicMock()
    turn.request.request_id = "req_123"
    turn.request.suspect_id = "suspect_001"
    turn.request.player_message = "Where were you?"
    
    return pipeline, adapter, turn

def test_pipeline_success_on_first_try(mock_pipeline_setup):
    pipeline, adapter, turn = mock_pipeline_setup
    
    # Adapter returns valid result
    adapter.generate.return_value = LLMResult(text="Valid reply", metrics=MagicMock(), truncated=False)
    
    # We mock validate to return no problems
    pipeline.validate = MagicMock(return_value=[])
    
    result = pipeline.generate(turn)
    
    assert result.is_fallback is False
    assert result.attempts == 1
    assert result.draft.content == "Valid reply"

def test_pipeline_fallback_on_llm_error(mock_pipeline_setup):
    pipeline, adapter, turn = mock_pipeline_setup
    
    # Adapter raises an error
    adapter.generate.side_effect = LLMError("Model failed")
    
    result = pipeline.generate(turn)
    
    assert result.is_fallback is True
    assert result.attempts == 2 # Tried twice
    # The fallback should return one of the safe lines
    assert result.draft is not None