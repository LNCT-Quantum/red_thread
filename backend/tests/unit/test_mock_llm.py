import pytest
import asyncio
from shared.contracts.dialogue import (
    DialogueRequest, DialogueDraft, GenerationMetrics
)
from shared.contracts.errors import ContractValidationError

# ---------------------------------------------------------
# 1. MOCK LLM PROVIDER (fake AI)
# ---------------------------------------------------------
class MockLLMProvider:
    def __init__(self, mode="valid"):
        self.mode = mode

    async def generate_stream(self, messages: list):
        if self.mode == "valid":
            # Ek sahi JSON jo schema mein fit ho
            yield '{"dialogue": "I was in the library.", '
            yield '"revealed_fact_ids": ["fact_001"], '
            yield '"deception_flag": false}'
        
        elif self.mode == "unauthorized_fact":
            # Galat Fact ID (NPC does not know this )
            yield '{"dialogue": "The killer is the doctor!", '
            yield '"revealed_fact_ids": ["fact_999"], ' 
            yield '"deception_flag": false}'
            
        elif self.mode == "malformed_json":
            # Adhura JSON (Bracket band nahi hua)
            yield '{"dialogue": "I was in the library.", '
            yield '"revealed_fact_ids": ["fact_001"'
            
        elif self.mode == "timeout":
            # 5 second ka delay (Test timeout simulate)
            await asyncio.sleep(5)
            yield '{"dialogue": "Late response", "revealed_fact_ids": [], "deception_flag": false}'


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
        authorized_fact_ids=("fact_001",),
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


# ---------------------------------------------------------
# 3. TESTS (Mock LLM and Validation)
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_llm_valid_mode_returns_correct_stream():
    # Check karo ki Mock LLM sahi stream de raha hai
    mock_llm = MockLLMProvider(mode="valid")
    full_response = ""
    async for token in mock_llm.generate_stream(messages=[]):
        full_response += token
    
    assert '"revealed_fact_ids": ["fact_001"]' in full_response

@pytest.mark.asyncio
async def test_validator_rejects_unauthorized_fact_from_llm(sample_request, valid_metrics):
    # Agar LLM unauthorized fact bhejta hai, toh Validator ko reject karna chahiye
    mock_llm = MockLLMProvider(mode="unauthorized_fact")
    
    # (Yeh simulation hai ki hum LLM se JSON utha kar load kar rahe hain)
    draft = DialogueDraft(
        request_id="req_123",
        suspect_id="suspect_001",
        content="The killer is the doctor!",
        cited_fact_ids=("fact_999",), # Unauthorized
        cited_clue_ids=(),
        metrics=valid_metrics
    )
    
    # Draft ko request ke against validate karo
    with pytest.raises(ContractValidationError) as exc_info:
        draft.validate_against_request(sample_request)
    
    assert "DRAFT_UNAUTHORIZED_FACT" in str(exc_info.value)

@pytest.mark.asyncio
async def test_malformed_json_handling():
    # if incommplete json is sent to LLM , toh parser error throw kare (yahan hum sirf stream check kar rahe hain)
    mock_llm = MockLLMProvider(mode="malformed_json")
    full_response = ""
    async for token in mock_llm.generate_stream(messages=[]):
        full_response += token
    
    # Verify karo ki JSON incomplete hai (closing bracket missing)
    assert full_response.endswith('["fact_001"') 
    assert "}" not in full_response

@pytest.mark.asyncio
async def test_timeout_simulation():
    # Timeout ka test (Hum 1 second ka timeout rakhenge)
    mock_llm = MockLLMProvider(mode="timeout")
    
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            anext(mock_llm.generate_stream(messages=[])), 
            timeout=1.0 # 1 second
        )