import logging
import pytest
from backend.shared.contracts.dialogue import DialogueRequest, DialogueDraft, GenerationMetrics
from backend.shared.contracts.errors import ContractValidationError
from backend.shared.contracts.api import APIResponse, APIError

# ---------------------------------------------------------
# 1. FALLBACK HANDLER (later module 12)
# ---------------------------------------------------------
class FallbackHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_fallback_response(self, request: DialogueRequest, error: Exception) -> APIResponse:
        # 1. Error ko log karo (caplog isko pakdega)
        self.logger.error(f"Validation failed for request {request.request_id}. Error: {error}")
        
        # 2. Safe fallback response create
        fallback_draft = DialogueDraft(
            request_id=request.request_id,
            suspect_id=request.suspect_id,
            content="I refuse to speak further without my solicitor.", # In-character safe line
            cited_fact_ids=(),
            cited_clue_ids=(),
            metrics=GenerationMetrics(
                model_id="fallback",
                time_to_first_token_ms=0.0,
                generation_time_ms=0.0,
                prompt_tokens=0
            )
        )
        
        # 3. APIResponse mein wrap karke return karo
        return APIResponse(
            request_id=request.request_id,
            success=False,
            data=None,
            error=APIError(
                code="VALIDATION_FAILED",
                message="LLM response was invalid. Fallback used.",
                details=(str(error),)
            )
        )

# ---------------------------------------------------------
# 2. FIXTURES
# ---------------------------------------------------------
@pytest.fixture
def sample_request():
    return DialogueRequest(
        request_id="req_123",
        case_id="case_001",
        suspect_id="suspect_001",
        player_message="Where were you?",
        authorized_fact_ids=("fact_001",)
    )

# ---------------------------------------------------------
# 3. TESTS (Fallback & Logging)
# ---------------------------------------------------------

def test_fallback_triggers_and_logs_error(caplog, sample_request):
    # caplog ko ERROR level par set karo taaki hum logs pakad sakein
    caplog.set_level(logging.ERROR)
    
    handler = FallbackHandler()
    dummy_error = ContractValidationError("Unauthorized fact cited.", code="DRAFT_UNAUTHORIZED_FACT")
    
    # Fallback trigger karo
    response = handler.generate_fallback_response(sample_request, dummy_error)
    
    # 1. Verify karo ki response fallback hai
    assert response.success is False
    assert response.error is not None
    assert response.error.code == "VALIDATION_FAILED"
    
    # 2. Verify karo ki log generate hua hai (caplog)
    assert "Validation failed for request req_123" in caplog.text
    assert "DRAFT_UNAUTHORIZED_FACT" in caplog.text