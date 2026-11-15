# File: backend/tests/unit/test_fallback_and_logging.py
import pytest
import logging
from unittest.mock import MagicMock

from shared.contracts.dialogue import DialogueRequest, GenerationMetrics
from src.dialogue_generator.response_validator import fallback_draft, FALLBACK_LINES
from src.dialogue_generator.pipeline import DialoguePipeline
from src.dialogue_generator.llm_adapter import LLMError

def test_fallback_draft_generates_safe_reply():
    """
    QA Note: Verify that the fallback_draft returns a safe reply.
    """
    request = DialogueRequest(
        request_id="req_fallback_001", case_id="case_001", suspect_id="suspect_001", 
        player_message="Tell me the secret.", authorized_fact_ids=(), presented_clue_ids=()
    )
    
    draft = fallback_draft(request)
    
    # Verify the draft content is one of the predefined safe fallback lines
    assert draft.content in FALLBACK_LINES
    assert len(draft.cited_fact_ids) == 0
    assert len(draft.cited_clue_ids) == 0
    assert draft.metrics.model_id == "fallback"

def test_pipeline_logs_warning_on_fallback(caplog):
    """
    QA Note: Verify that when the LLM fails, the DialoguePipeline triggers fallback AND logs it.
    """
    caplog.set_level(logging.WARNING)
    
    # Setup mock engine and failing adapter
    engine = MagicMock()
    failing_adapter = MagicMock()
    failing_adapter.generate.side_effect = LLMError("Simulated LLM connection timeout")
    
    pipeline = DialoguePipeline(engine, adapter=failing_adapter)
    
    # Setup a solid mock turn with string values, not MagicMock
    turn = MagicMock()
    turn.request.request_id = "req_timeout_test"
    turn.request.suspect_id = "suspect_001"
    turn.request.player_message = "Test message"
    
    pipeline.build_context = MagicMock(return_value=MagicMock(hidden_statements=()))
    
    # Run pipeline
    result = pipeline.generate(turn)
    
    assert result.is_fallback is True
    assert result.attempts == 2 
    assert "dialogue fallback for req_timeout_test" in caplog.text
    assert "Simulated LLM connection timeout" in caplog.text