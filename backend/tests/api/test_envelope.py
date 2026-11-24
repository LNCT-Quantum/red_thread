"""Envelope, serialization and error-translation units (no HTTP)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import pytest

from api.config import Settings
from api.envelope import failure, success, to_jsonable
from api.errors import translate_domain_error
from shared.contracts.errors import (
    ContractValidationError,
    ExternalServiceError,
    PermissionDeniedError,
    RedThreadError,
    ResourceNotFoundError,
    StateConflictError,
)
from shared.contracts.game_state import GameState


class Color(Enum):
    RED = "red"


@dataclass(frozen=True, slots=True)
class Inner:
    when: datetime
    color: Color
    ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Outer:
    inner: Inner
    tags: frozenset
    maybe: None = None


def test_to_jsonable_handles_nested_contracts_enums_tuples_and_datetimes():
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    value = Outer(Inner(stamp, Color.RED, ("a", "b")), frozenset({"z", "y"}))
    result = to_jsonable(value)
    assert result == {
        "inner": {"when": stamp.isoformat(), "color": "red", "ids": ["a", "b"]},
        "tags": ["y", "z"],
        "maybe": None,
    }
    json.dumps(result)  # must be valid JSON


def test_real_game_state_contract_serializes():
    state = GameState(game_id="g", case_id="c", discovered_clue_ids=("clue_001",))
    assert to_jsonable(state)["discovered_clue_ids"] == ["clue_001"]


def test_unserializable_value_is_rejected_not_silently_dropped():
    with pytest.raises(TypeError):
        to_jsonable(object())


def test_success_and_failure_follow_the_contract():
    ok_body = json.loads(success("req_12345678", {"x": 1}).body)
    assert ok_body == {
        "request_id": "req_12345678", "success": True, "data": {"x": 1},
        "error": None, "schema_version": "1.0",
    }
    bad = json.loads(failure("req_12345678", 404, "X", "msg", ["a", "a", "  ", "b"]).body)
    assert bad["success"] is False and bad["data"] is None
    assert bad["error"]["details"] == ["a", "b"]  # duplicates / blanks removed (APIError forbids them)


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ResourceNotFoundError("x", code="GAME_SESSION_NOT_FOUND"), 404, "SESSION_NOT_FOUND"),
        (StateConflictError("x", code="REVISION_CONFLICT", details=("expected 1, stored 2",)), 409, "REVISION_CONFLICT"),
        (PermissionDeniedError("x", code="CLUE_LOCKED", details=("clue_005",)), 403, "CLUE_LOCKED"),
        (StateConflictError("x", code="GAME_STATE_FOREIGN_ID"), 500, "SESSION_STATE_INVALID"),
        (ResourceNotFoundError("x"), 404, "RESOURCE_NOT_FOUND"),
        (PermissionDeniedError("x", code="SOMETHING_NEW"), 403, "ACCESS_DENIED"),
        (StateConflictError("x", code="SOMETHING_NEW"), 409, "STATE_CONFLICT"),
        (ContractValidationError("x"), 400, "INVALID_REQUEST"),
        (ExternalServiceError("x"), 503, "SERVICE_UNAVAILABLE"),
        (RedThreadError("x"), 500, "INTERNAL_ERROR"),
    ],
)
def test_domain_errors_map_to_status_and_public_code(exc, status, code):
    api_error = translate_domain_error(exc)
    assert (api_error.status_code, api_error.code) == (status, code)


def test_domain_error_details_do_not_leak_unless_explicitly_allowed():
    leaky = ResourceNotFoundError(
        "Case directory not found", details=("/srv/app/backend/case_data/case_999",), code="CASE_NOT_FOUND"
    )
    assert translate_domain_error(leaky).details == ()
    unmet = PermissionDeniedError(
        "Stage requirements are not met.", details=("clue not discovered: clue_023",),
        code="STAGE_REQUIREMENTS_UNMET",
    )
    translated = translate_domain_error(unmet)
    assert translated.details == () and "clue_023" not in translated.message


def test_settings_from_env_parses_and_validates():
    settings = Settings.from_env({
        "API_CORS_ORIGINS": "https://a.example, https://b.example",
        "API_DIALOGUE_TIMEOUT_S": "42",
        "API_ENABLE_DOCS": "false",
        "API_CASE_IDS": "case_001",
    })
    assert settings.cors_origins == ("https://a.example", "https://b.example")
    assert settings.dialogue_timeout_s == 42.0 and settings.enable_docs is False
    assert settings.case_ids == ("case_001",)
    assert Settings.from_env({}).cors_origins == ()  # no hard-coded origins
    with pytest.raises(ValueError):
        Settings.from_env({"API_DIALOGUE_TIMEOUT_S": "fast"})
    with pytest.raises(ValueError):
        Settings.from_env({"API_ENABLE_DOCS": "maybe"})
