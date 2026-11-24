from __future__ import annotations

from .conftest import API, discover, err, ok, new_session, talk


def test_create_session_returns_201_location_and_initial_state(client):
    response = client.post(f"{API}/sessions", json={"case_id": "case_001"})
    data = ok(response, 201)
    assert response.headers["location"] == f"{API}/sessions/{data['session_id']}"
    state = data["state"]
    assert state["session_id"] == data["session_id"] and state["case_id"] == "case_001"
    assert state["revision"] == 0 and state["status"] == "active"
    assert state["stage"]["stage_id"] == "stage_1" and state["stage"]["index"] == 1
    assert state["discovered_clue_ids"] == [] and state["interviewed_suspect_ids"] == []


def test_create_session_unknown_case(client):
    err(client.post(f"{API}/sessions", json={"case_id": "case_404"}), 404, "CASE_NOT_FOUND")


def test_invalid_create_payloads(client):
    err(client.post(f"{API}/sessions", json={}), 422, "REQUEST_VALIDATION_ERROR")
    err(client.post(f"{API}/sessions", json={"case_id": ""}), 422, "REQUEST_VALIDATION_ERROR")
    err(client.post(f"{API}/sessions", json={"case_id": 5}), 422, "REQUEST_VALIDATION_ERROR")
    error = err(client.post(f"{API}/sessions", json={"case_id": "case_001", "player_name": "x"}), 422, "REQUEST_VALIDATION_ERROR")
    assert any("player_name" in d for d in error["details"])
    err(client.post(f"{API}/sessions", content="{oops", headers={"content-type": "application/json"}), 400, "INVALID_JSON")
    err(client.post(f"{API}/sessions", content=b"x" * 20000, headers={"content-type": "application/json"}), 413, "PAYLOAD_TOO_LARGE")


def test_get_session_and_unknown_session(client):
    sid = new_session(client)
    assert ok(client.get(f"{API}/sessions/{sid}"))["session_id"] == sid
    for suffix in ("", "/history", "/progress", "/progression", "/unlocks", "/clues", "/evidence"):
        err(client.get(f"{API}/sessions/does-not-exist{suffix}"), 404, "SESSION_NOT_FOUND")
    err(client.post(f"{API}/sessions/nope/dialogue", json={"npc_id": "suspect_001", "message": "hi"}), 404, "SESSION_NOT_FOUND")
    err(discover(client, "nope", "clue_001"), 404, "SESSION_NOT_FOUND")
    err(client.delete(f"{API}/sessions/nope"), 404, "SESSION_NOT_FOUND")


def test_delete_session(client):
    sid = new_session(client)
    assert ok(client.delete(f"{API}/sessions/{sid}")) == {"session_id": sid, "deleted": True}
    err(client.get(f"{API}/sessions/{sid}"), 404, "SESSION_NOT_FOUND")
    err(client.delete(f"{API}/sessions/{sid}"), 404, "SESSION_NOT_FOUND")


def test_sessions_are_isolated(client):
    a, b = new_session(client), new_session(client)
    assert a != b
    ok(discover(client, a, "clue_001"))
    talk(client, a, "suspect_002", "Where were you?")
    assert ok(client.get(f"{API}/sessions/{a}"))["discovered_clue_ids"] == ["clue_001"]
    assert ok(client.get(f"{API}/sessions/{b}"))["discovered_clue_ids"] == []
    assert ok(client.get(f"{API}/sessions/{b}"))["revision"] == 0
    assert ok(client.get(f"{API}/sessions/{b}/history"))["total"] == 0
    assert ok(client.get(f"{API}/sessions/{a}/history"))["total"] == 2
    ok(client.delete(f"{API}/sessions/{b}"))
    assert ok(client.get(f"{API}/sessions/{a}"))["session_id"] == a


def test_progress_initial(client):
    sid = new_session(client)
    data = ok(client.get(f"{API}/sessions/{sid}/progress"))
    assert data["clues"] == {"discovered": 0, "total": 23, "collectable_now": 5}
    assert data["interviews_total"] == 3 and data["interviews_completed"] == []
    assert data["next_stage"] == {"requirements_total": 3, "requirements_met": 0}


def test_history_filters_and_paging(client):
    sid = new_session(client)
    talk(client, sid, "suspect_001", "one")
    talk(client, sid, "suspect_002", "two")
    talk(client, sid, "suspect_001", "three")
    data = ok(client.get(f"{API}/sessions/{sid}/history"))
    assert data["total"] == 6
    assert {c["npc_id"]: c["turn_count"] for c in data["conversations"]} == {"suspect_001": 2, "suspect_002": 1}
    only = ok(client.get(f"{API}/sessions/{sid}/history", params={"npc_id": "suspect_001"}))
    assert [m["content"] for m in only["messages"] if m["speaker_type"] == "player"] == ["one", "three"]
    assert [m["turn_number"] for m in only["messages"]] == [1, 1, 2, 2]
    page = ok(client.get(f"{API}/sessions/{sid}/history", params={"limit": 2, "offset": 2}))
    assert len(page["messages"]) == 2 and page["total"] == 6
    err(client.get(f"{API}/sessions/{sid}/history", params={"npc_id": "ghost"}), 404, "NPC_NOT_FOUND")
    err(client.get(f"{API}/sessions/{sid}/history", params={"limit": 0}), 422, "REQUEST_VALIDATION_ERROR")
