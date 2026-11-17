# File: backend/tests/unit/test_response_validator.py
import pytest
from src.dialogue_generator.response_validator import validate
from src.dialogue_generator.context_builder import DialogueContext
from shared.contracts.dialogue import DialogueDraft, GenerationMetrics

@pytest.fixture
def dummy_ctx():
    return DialogueContext(
        suspect=None, facts=(), clues=(), reactions=(), history=(),
        player_message="Test", 
        hidden_statements=("The killer is the doctor.",) 
    )

@pytest.fixture
def dummy_metrics():
    # Contract requires a valid GenerationMetrics object, not None
    return GenerationMetrics(
        model_id="test", time_to_first_token_ms=0.0, 
        generation_time_ms=0.0, prompt_tokens=0, completion_tokens=0
    )

def test_validator_rejects_empty_reply(dummy_ctx, dummy_metrics):
    draft = DialogueDraft(
        request_id="1", suspect_id="1", content="...", 
        cited_fact_ids=(), cited_clue_ids=(), metrics=dummy_metrics
    )
    problems = validate(draft, dummy_ctx)
    assert "empty reply" in problems

def test_validator_rejects_ai_speak(dummy_ctx, dummy_metrics):
    draft = DialogueDraft(
        request_id="1", suspect_id="1", content="As an AI language model, I cannot tell you.", 
        cited_fact_ids=(), cited_clue_ids=(), metrics=dummy_metrics
    )
    problems = validate(draft, dummy_ctx)
    assert "out of character or exposes internal ids" in problems

def test_validator_rejects_internal_ids(dummy_ctx, dummy_metrics):
    draft = DialogueDraft(
        request_id="1", suspect_id="1", content="I know about fact_001.", 
        cited_fact_ids=(), cited_clue_ids=(), metrics=dummy_metrics
    )
    problems = validate(draft, dummy_ctx)
    assert "out of character or exposes internal ids" in problems

def test_validator_detects_hidden_fact_leak(dummy_ctx, dummy_metrics):
    # If the AI copies 5+ words from a hidden fact, it should be flagged
    leak_text = "I heard that the killer is the doctor but I won't say."
    draft = DialogueDraft(
        request_id="1", suspect_id="1", content=leak_text, 
        cited_fact_ids=(), cited_clue_ids=(), metrics=dummy_metrics
    )
    problems = validate(draft, dummy_ctx)
    assert "repeats a fact this NPC must not know" in problems