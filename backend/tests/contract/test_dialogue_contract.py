import pytest
from datetime import datetime
from shared.contracts.dialogue import (
    DialogueRequest, DialogueDraft, GenerationMetrics
)
from shared.contracts.errors import ContractValidationError

@pytest.fixture
def sample_request():
    # one basic request in which only  fact_001 allowed 
    return DialogueRequest(
        request_id="req_123",
        case_id="case_001",
        suspect_id="suspect_001",
        player_message="Where were you?",
        authorized_fact_ids=("fact_001",), # allowed 
        presented_clue_ids=()
    )

@pytest.fixture
def valid_metrics():
    return GenerationMetrics(
        model_id="qwen",
        time_to_first_token_ms=500.0,
        generation_time_ms=2000.0,
        prompt_tokens=10
    )

def test_draft_with_authorized_fact_passes(sample_request, valid_metrics):
    # 1. valid draft which use  allowed fact (fact_001)
    draft = DialogueDraft(
        request_id="req_123",
        suspect_id="suspect_001",
        content="I was in the library.",
        cited_fact_ids=("fact_001",),
        cited_clue_ids=(),
        metrics=valid_metrics
    )
    # Validate , no error should come
    draft.validate_against_request(sample_request)

def test_draft_with_unauthorized_fact_fails(sample_request, valid_metrics):
    # 2.  draft which cite wrong  fact (fact_999)
    draft = DialogueDraft(
        request_id="req_123",
        suspect_id="suspect_001",
        content="I was in the library.",
        cited_fact_ids=("fact_999",), # not allowed
        cited_clue_ids=(),
        metrics=valid_metrics
    )
    #ContractValidationError 
    with pytest.raises(ContractValidationError) as exc_info:
        draft.validate_against_request(sample_request)
    
    assert "not authorized for this request" in str(exc_info.value)