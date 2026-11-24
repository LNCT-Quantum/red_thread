from __future__ import annotations

from .conftest import API, discover, err, ok, new_session


def test_discover_unlocked_clue(client):
    sid = new_session(client)
    data = ok(discover(client, sid, "clue_001"))
    assert data["clue"]["clue_id"] == "clue_001" and data["clue"]["description"]
    assert data["already_discovered"] is False
    assert data["state"]["revision"] == 1 and data["state"]["discovered_clue_ids"] == ["clue_001"]
    assert "reliability" not in data["clue"] and "related_fact_ids" not in data["clue"]


def test_locked_clue_cannot_be_unlocked_by_id(client):
    sid = new_session(client)
    for locked in ("clue_005", "clue_009", "clue_014", "clue_023", "clue_006"):
        error = err(discover(client, sid, locked), 403, "CLUE_LOCKED")
        assert error["details"] == []
    state = ok(client.get(f"{API}/sessions/{sid}"))
    assert state["discovered_clue_ids"] == [] and state["revision"] == 0


def test_unknown_clue_and_idempotent_rediscovery(client):
    sid = new_session(client)
    err(discover(client, sid, "clue_999"), 404, "CLUE_NOT_FOUND")
    ok(discover(client, sid, "clue_001"))
    again = ok(discover(client, sid, "clue_001"))
    assert again["already_discovered"] is True and again["state"]["revision"] == 1


def test_revision_conflict(client):
    sid = new_session(client)
    ok(discover(client, sid, "clue_001"))
    error = err(discover(client, sid, "clue_004", expected_revision=0), 409, "REVISION_CONFLICT")
    assert "expected revision 0" in error["details"][0]
    ok(discover(client, sid, "clue_004", expected_revision=1))
    err(discover(client, sid, "clue_002", expected_revision="1"), 422, "REQUEST_VALIDATION_ERROR")


def test_clue_lists_and_evidence(client):
    sid = new_session(client)
    ok(discover(client, sid, "clue_012"))
    clues = ok(client.get(f"{API}/sessions/{sid}/clues"))
    assert clues["discovered_count"] == 1 and clues["total_count"] == 23
    assert clues["clues"][0]["clue_id"] == "clue_012"
    evidence = ok(client.get(f"{API}/sessions/{sid}/evidence"))
    assert [c["clue_id"] for c in evidence["collected"]] == ["clue_012"]
    assert {c["clue_id"] for c in evidence["collectable"]} == {"clue_001", "clue_002", "clue_004", "clue_013"}
    assert all("description" not in c for c in evidence["collectable"])


def test_discovery_advances_stage_through_the_progression_gate(client):
    sid = new_session(client)
    ok(discover(client, sid, "clue_001"))
    ok(discover(client, sid, "clue_004"))
    data = ok(discover(client, sid, "clue_012"))
    assert [s["stage_id"] for s in data["newly_unlocked_stages"]] == ["stage_2"]
    assert data["state"]["stage"]["stage_id"] == "stage_2"
    assert {"clue_005", "clue_007", "clue_011"} <= {c["clue_id"] for c in data["newly_collectable_clues"]}
    ok(discover(client, sid, "clue_005"))  # now unlocked


def test_progress_cannot_be_forged_by_other_session(client):
    a, b = new_session(client), new_session(client)
    for c in ("clue_001", "clue_004", "clue_012"):
        ok(discover(client, a, c))
    err(discover(client, b, "clue_005"), 403, "CLUE_LOCKED")
