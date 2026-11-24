from __future__ import annotations

import json

from .conftest import API, err, new_session, ok


def test_request_id_is_generated_and_echoed(client):
    response = client.get(f"{API}/health")
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-request-id"].startswith("req_")
    other = client.get(f"{API}/health")
    assert other.headers["x-request-id"] != response.headers["x-request-id"]


def test_client_supplied_request_id_is_reused_only_when_safe(client):
    good = client.get(f"{API}/health", headers={"X-Request-ID": "frontend-trace-0001"})
    assert good.json()["request_id"] == "frontend-trace-0001"
    bad = client.get(f"{API}/health", headers={"X-Request-ID": "bad id with spaces <script>"})
    assert bad.json()["request_id"].startswith("req_")


def test_unknown_route_and_wrong_method_use_the_envelope(client):
    err(client.get(f"{API}/nothing-here"), 404, "ROUTE_NOT_FOUND")
    err(client.put(f"{API}/cases"), 405, "METHOD_NOT_ALLOWED")


def test_unexpected_exception_returns_safe_500(client):
    secret = "/srv/redthread/backend/secrets/key.txt"

    def boom(*args, **kwargs):
        raise RuntimeError(f"database exploded reading {secret}")

    sid = new_session(client)
    client.app.state.container.games.get_session = boom
    response = client.get(f"{API}/sessions/{sid}")
    error = err(response, 500, "INTERNAL_ERROR")
    assert error["message"] == "An unexpected error occurred" and error["details"] == []
    for leaked in (secret, "database exploded", "Traceback", "RuntimeError", ".py"):
        assert leaked not in response.text


def test_unexpected_exception_in_dialogue_is_safe_500(client, llm):
    sid = new_session(client)

    def boom(prompt, *a, **k):
        raise ZeroDivisionError("kaboom /etc/passwd")

    llm.responder = boom
    response = client.post(f"{API}/sessions/{sid}/dialogue", json={"npc_id": "suspect_001", "message": "hi"})
    err(response, 500, "INTERNAL_ERROR")
    assert "kaboom" not in response.text and "passwd" not in response.text
    assert ok(client.get(f"{API}/sessions/{sid}"))["revision"] == 0


def test_cors_allows_configured_origin_only_and_covers_errors(client):
    pre = client.options(
        f"{API}/sessions",
        headers={"Origin": "http://frontend.test", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "http://frontend.test"
    denied = client.options(
        f"{API}/sessions",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers
    failing = client.get(f"{API}/cases/nope", headers={"Origin": "http://frontend.test"})
    assert failing.status_code == 404
    assert failing.headers["access-control-allow-origin"] == "http://frontend.test"
    assert "x-request-id" in failing.headers["access-control-expose-headers"].lower()


def test_no_cors_headers_when_no_origins_configured(make_client, llm):
    client = make_client(llm, cors_origins=())
    response = client.get(f"{API}/health", headers={"Origin": "http://anything.test"})
    assert "access-control-allow-origin" not in response.headers


def test_openapi_documents_every_required_endpoint(client):
    paths = client.get(f"{API}/openapi.json").json()["paths"]
    expected = {
        ("get", "/health"), ("get", "/health/ready"), ("get", "/cases"), ("get", "/cases/{case_id}"),
        ("get", "/cases/{case_id}/suspects"), ("get", "/cases/{case_id}/clues"),
        ("get", "/cases/{case_id}/timeline"), ("get", "/cases/{case_id}/facts"),
        ("post", "/sessions"), ("get", "/sessions/{session_id}"), ("delete", "/sessions/{session_id}"),
        ("get", "/sessions/{session_id}/history"), ("get", "/sessions/{session_id}/progress"),
        ("post", "/sessions/{session_id}/dialogue"), ("get", "/sessions/{session_id}/clues"),
        ("post", "/sessions/{session_id}/clues/{clue_id}/discover"),
        ("get", "/sessions/{session_id}/evidence"), ("get", "/sessions/{session_id}/progression"),
        ("get", "/sessions/{session_id}/unlocks"),
        ("post", "/sessions/{session_id}/interviews/{suspect_id}/complete"),
    }
    actual = {(m, p[len(API):]) for p, ms in paths.items() for m in ms}
    assert expected <= actual


def test_docs_can_be_disabled(make_client, llm):
    client = make_client(llm, enable_docs=False)
    assert client.get(f"{API}/docs").status_code == 404
    assert client.get(f"{API}/openapi.json").status_code == 404


def test_responses_are_not_cacheable(client):
    response = client.get(f"{API}/cases")
    assert response.headers["cache-control"] == "no-store"
    json.loads(response.text)
