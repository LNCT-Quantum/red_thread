"""API test fixtures.

The LLM is faked at the lowest level (the ``LocalLLMEngine`` interface), so the REAL
``LLMAdapter``, ``DialoguePipeline``, ``FactExtractor`` and response validator all run.
No network, Ollama or API key is needed.
"""

from __future__ import annotations

import json
import re
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.config import Settings

API = "/api/v1"
SAFE_REPLY = "I have nothing to hide, detective. Ask what you like."


def json_reply(content: str = SAFE_REPLY, facts=(), clues=()) -> str:
    return json.dumps({"content": content, "cited_fact_ids": list(facts), "cited_clue_ids": list(clues)})


class FakeLLMEngine:
    """Scripted stand-in for ``LocalLLMEngine`` (``check_health`` + ``stream_generate``)."""

    def __init__(self, responder=None, healthy: bool = True, delay: float = 0.0) -> None:
        self.config = SimpleNamespace(model_name="fake-model")
        self.responder = responder or (lambda prompt: json_reply())
        self.healthy = healthy
        self.delay = delay
        self.prompts: list[str] = []
        self.calls = 0
        self.entered = threading.Event()
        self.release: threading.Event | None = None

    def check_health(self) -> bool:
        return self.healthy

    def stream_generate(self, prompt, cache_prompt=None, response_format=None):
        self.calls += 1
        self.prompts.append(prompt)
        self.entered.set()
        if self.release is not None:
            self.release.wait(timeout=5)
        if self.delay:
            time.sleep(self.delay)
        text = self.responder(prompt)
        yield {"type": "token", "token": text, "ttft_ms": 1.0}
        yield {
            "type": "complete",
            "text": text,
            "truncated": False,
            "metrics": {"client_ttft_ms": 1.0, "prompt_eval_count": 10, "eval_count": 5},
        }


def make_settings(**overrides) -> Settings:
    base = dict(
        cors_origins=("http://frontend.test",),
        dialogue_timeout_s=5.0,
        log_level="WARNING",
        enable_docs=True,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def llm() -> FakeLLMEngine:
    return FakeLLMEngine()


@pytest.fixture
def make_client():
    clients: list[TestClient] = []

    def factory(llm_engine, **settings_overrides) -> TestClient:
        app = create_app(make_settings(**settings_overrides), llm_engine=llm_engine)
        client = TestClient(app, raise_server_exceptions=False)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.app.state.container.close()


@pytest.fixture
def client(make_client, llm) -> TestClient:
    return make_client(llm)


@pytest.fixture
def runtime(client):
    return client.app.state.container.registry.get("case_001")


# ----------------------------------------------------------------------- helpers
def assert_envelope(response, *, success: bool, status: int | None = None) -> dict:
    """Every response must use the shared envelope, success or failure."""
    if status is not None:
        assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"request_id", "success", "data", "error", "schema_version"}
    assert body["success"] is success
    assert body["schema_version"] == "1.0"
    assert body["request_id"] == response.headers["x-request-id"]
    if success:
        assert body["error"] is None and body["data"] is not None
    else:
        assert body["data"] is None
        assert {"code", "message", "details"} <= set(body["error"])
    return body


def ok(response, status: int = 200):
    return assert_envelope(response, success=True, status=status)["data"]


def err(response, status: int, code: str):
    body = assert_envelope(response, success=False, status=status)
    assert body["error"]["code"] == code, body
    return body["error"]


def new_session(client: TestClient, case_id: str = "case_001") -> str:
    return ok(client.post(f"{API}/sessions", json={"case_id": case_id}), 201)["session_id"]


def discover(client, sid, clue_id, **body):
    return client.post(f"{API}/sessions/{sid}/clues/{clue_id}/discover", json=body or None)


def talk(client, sid, npc="suspect_001", message="Tell me about that night.", **extra):
    return client.post(f"{API}/sessions/{sid}/dialogue", json={"npc_id": npc, "message": message, **extra})


def fact_ids_in(prompt: str) -> set[str]:
    return set(re.findall(r"^\[(fact_\d{3})\]", prompt, flags=re.MULTILINE))


SUSPECTS = ("suspect_001", "suspect_002", "suspect_003")


def interview_all(client, sid):
    """Talk to each suspect once, then complete each interview (all through the API)."""
    results = []
    for suspect in SUSPECTS:
        assert talk(client, sid, suspect, "Walk me through your evening.").status_code == 200
        results.append(client.post(f"{API}/sessions/{sid}/interviews/{suspect}/complete"))
    return results


def play_to_stage_4(client) -> str:
    sid = new_session(client)
    for clue in ("clue_001", "clue_004", "clue_012", "clue_005", "clue_007", "clue_011"):
        assert discover(client, sid, clue).status_code == 200, clue
    interview_all(client, sid)
    for clue in ("clue_014", "clue_019", "clue_020"):
        assert discover(client, sid, clue).status_code == 200, clue
    return sid
