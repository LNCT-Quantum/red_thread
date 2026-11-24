from __future__ import annotations

from .conftest import API, discover, err, interview_all, ok, new_session, play_to_stage_4, talk


def test_initial_progression_and_unlocks(client):
    sid = new_session(client)
    prog = ok(client.get(f"{API}/sessions/{sid}/progression"))
    assert prog["current_stage"]["stage_id"] == "stage_1" and prog["total_stages"] == 5
    assert [s["stage_id"] for s in prog["unlocked_stages"]] == ["stage_1"]
    assert prog["is_final_stage"] is False
    assert prog["next_stage"] == {"requirements_total": 3, "requirements_met": 0}
    unlocks = ok(client.get(f"{API}/sessions/{sid}/unlocks"))
    assert unlocks["stage_id"] == "stage_1"
    assert {c["clue_id"] for c in unlocks["collectable_clues"]} == {"clue_001", "clue_002", "clue_004", "clue_012", "clue_013"}
    assert unlocks["discovered_clue_ids"] == []


def test_progression_does_not_name_next_stage_requirements(client):
    sid = new_session(client)
    text = client.get(f"{API}/sessions/{sid}/progression").text
    assert "required_clue_ids" not in text and "unmet" not in text
    assert "clue_001" not in text


def test_progression_updates_after_discovery(client):
    sid = new_session(client)
    ok(discover(client, sid, "clue_001"))
    assert ok(client.get(f"{API}/sessions/{sid}/progression"))["next_stage"]["requirements_met"] == 1
    ok(discover(client, sid, "clue_004"))
    ok(discover(client, sid, "clue_012"))
    prog = ok(client.get(f"{API}/sessions/{sid}/progression"))
    assert prog["current_stage"]["stage_id"] == "stage_2"
    assert [s["stage_id"] for s in prog["unlocked_stages"]] == ["stage_1", "stage_2"]
    unlocks = ok(client.get(f"{API}/sessions/{sid}/unlocks"))
    assert "clue_005" in {c["clue_id"] for c in unlocks["collectable_clues"]}


def test_no_endpoint_lets_the_client_set_progression_directly(client):
    sid = new_session(client)
    for method, path in (
        ("put", f"/sessions/{sid}/progression"),
        ("post", f"/sessions/{sid}/progression"),
        ("patch", f"/sessions/{sid}"),
        ("put", f"/sessions/{sid}"),
        ("post", f"/sessions/{sid}/unlocks"),
    ):
        response = getattr(client, method)(f"{API}{path}", json={"stage_id": "stage_5"})
        assert response.status_code in (404, 405), (method, path)
    assert ok(client.get(f"{API}/sessions/{sid}"))["stage"]["stage_id"] == "stage_1"


def test_interview_requires_real_conversation(client):
    sid = new_session(client)
    error = err(client.post(f"{API}/sessions/{sid}/interviews/suspect_001/complete"), 409, "INTERVIEW_NOT_READY")
    assert error["details"] == ["required_exchanges=1", "exchanges=0"]
    err(client.post(f"{API}/sessions/{sid}/interviews/ghost/complete"), 404, "NPC_NOT_FOUND")
    err(client.post(f"{API}/sessions/nope/interviews/suspect_001/complete"), 404, "SESSION_NOT_FOUND")
    assert ok(client.get(f"{API}/sessions/{sid}"))["interviewed_suspect_ids"] == []


def test_interview_completion_is_idempotent_and_unlocks_testimony(client):
    sid = new_session(client)
    talk(client, sid, "suspect_001")
    first = ok(client.post(f"{API}/sessions/{sid}/interviews/suspect_001/complete"))
    assert first["already_completed"] is False
    assert first["state"]["interviewed_suspect_ids"] == ["suspect_001"]
    assert {c["clue_id"] for c in first["newly_collectable_clues"]} >= {"clue_006"}
    again = ok(client.post(f"{API}/sessions/{sid}/interviews/suspect_001/complete"))
    assert again["already_completed"] is True
    assert again["state"]["revision"] == first["state"]["revision"]
    ok(discover(client, sid, "clue_006"))  # testimony clue now allowed


def test_interview_revision_conflict(client):
    sid = new_session(client)
    talk(client, sid, "suspect_001")
    err(client.post(f"{API}/sessions/{sid}/interviews/suspect_001/complete", json={"expected_revision": 0}), 409, "REVISION_CONFLICT")


def test_full_investigation_reaches_final_stage_through_the_api_only(client):
    sid = play_to_stage_4(client)
    state = ok(client.get(f"{API}/sessions/{sid}"))
    assert state["stage"]["stage_id"] == "stage_4"
    assert state["interviewed_suspect_ids"] == ["suspect_001", "suspect_002", "suspect_003"]
    last = None
    for clue in ("clue_008", "clue_009", "clue_010", "clue_023"):
        last = ok(discover(client, sid, clue))
    assert last["state"]["stage"]["stage_id"] == "stage_5"
    assert [s["stage_id"] for s in last["newly_unlocked_stages"]] == ["stage_5"]
    prog = ok(client.get(f"{API}/sessions/{sid}/progression"))
    assert prog["is_final_stage"] is True and prog["next_stage"] is None
    progress = ok(client.get(f"{API}/sessions/{sid}/progress"))
    assert progress["clues"]["discovered"] == len(progress["discovered_clues"]) > 10
    assert len(progress["conversations"]) == 3
