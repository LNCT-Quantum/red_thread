# File: backend/tests/contract/test_api_and_errors.py
import pytest
from shared.contracts.api import APIResponse, APIError
from shared.contracts.errors import ContractValidationError

def test_api_response_success():
    # A successful response must have data and no error
    res = APIResponse(request_id="req_1", success=True, data={"msg": "ok"})
    assert res.success is True
    assert res.error is None
    assert res.data == {"msg": "ok"}

def test_api_response_fails_if_error_given_on_success():
    # If success is True, providing an error should fail
    with pytest.raises(ValueError, match="'error' must be None when 'success' is True"):
        APIResponse(
            request_id="req_1", 
            success=True, 
            error=APIError(code="ERR", message="Bad")
        )

def test_error_formatting():
    # Test that our custom error string formats correctly
    err = ContractValidationError(message="Data invalid", code="DATA_ERR", details=("missing ID",))
    assert str(err) == "[DATA_ERR] Data invalid (missing ID)"