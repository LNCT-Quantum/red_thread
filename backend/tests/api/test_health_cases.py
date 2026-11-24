from __future__ import annotations

import json

from .conftest import API, assert_envelope, err, make_settings, ok, new_session, talk

FORBIDDEN_KEYS = {
    "related_fact_ids", "reliability", "authorized_fact_ids", "secret_fact_ids", "known_fact_ids",
    "unknown_fact_ids", "knowledge_notes", "evidence_reactions", "background", "speech_style",
    "personality_traits", "importance", "related_entity_ids", "completed_objective_ids",
    "source_entity_id", "metrics", "prompt", "cited_fact_ids", "cited_clue_ids",
}


def all_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from all_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from all_keys(v)


def test_health(client):
    data = ok(client.get(f"{API}/health"))
    assert data["status"] == "ok" and data["version"]


def test_ready_when_components_ok(client):
    data = ok(client.get(f"{API}/health/ready"))
    assert data["ready"] is True
    assert data["components"]["llm"]["status"] == "ok"
    assert "in-memory" in data["components"]["session_store"]["detail"]


def test_not_ready_when_llm_down(make_client, llm):
    llm.healthy = False
    error = err(make_client(llm).get(f"{API}/health/ready"), 503, "NOT_READY")
    assert any("llm" in d for d in error["details"])


def test_list_and_get_case(client):
    data = ok(client.get(f"{API}/cases"))
    assert data["count"] == 1 and data["items"][0]["case_id"] == "case_001"
    case = ok(client.get(f"{API}/cases/case_001"))
    assert case["title"] == "The Silent Witness" and case["suspect_count"] == 3
    assert "fact_ids" not in case and "clue_ids" not in case


def test_invalid_case_ids_are_404_everywhere(client):
    for suffix in ("", "/suspects", "/clues", "/facts", "/timeline"):
        err(client.get(f"{API}/cases/case_999{suffix}"), 404, "CASE_NOT_FOUND")
    # traversal attempts: either no route matches or the ID is just a failed dictionary lookup
    err(client.get(f"{API}/cases/..%2F..%2Fetc"), 404, "ROUTE_NOT_FOUND")
    err(client.get(f"{API}/cases/..%5C..%5Cetc"), 404, "CASE_NOT_FOUND")


def test_suspects_are_public_profiles_only(client):
    items = ok(client.get(f"{API}/cases/case_001/suspects"))["items"]
    assert [s["suspect_id"] for s in items] == ["suspect_001", "suspect_002", "suspect_003"]
    assert set(items[0]) == {"suspect_id", "name", "age", "occupation", "public_description", "relationship_to_victim"}


def test_case_clues_are_titles_only_and_initial(client):
    items = ok(client.get(f"{API}/cases/case_001/clues"))["items"]
    assert [c["clue_id"] for c in items] == ["clue_001", "clue_002", "clue_004", "clue_012", "clue_013"]
    assert all("description" not in c for c in items)


def test_public_endpoints_never_leak_hidden_information(client, runtime):
    engine, public = runtime.engine, runtime.public
    hidden_statements = [f.statement for f in engine.list_facts() if f.fact_id not in public.fact_ids]
    hidden_titles = [
        c.title for c in engine.list_clues() if c.clue_id not in public.clue_ids
    ]
    hidden_events = [
        e.event_description for e in engine.list_timeline_events()
        if e.timeline_event_id not in public.event_ids
    ]
    blob = ""
    for suffix in ("", "/suspects", "/clues", "/facts", "/timeline"):
        response = client.get(f"{API}/cases/case_001{suffix}")
        body = response.json()
        assert not (set(all_keys(body)) & FORBIDDEN_KEYS)
        blob += json.dumps(body)
    for text in hidden_statements + hidden_titles + hidden_events:
        assert text not in blob
    facts = ok(client.get(f"{API}/cases/case_001/facts"))["items"]
    assert {f["fact_id"] for f in facts} == set(public.fact_ids) and len(facts) == 7
    timeline = ok(client.get(f"{API}/cases/case_001/timeline"))["items"]
    assert [e["event_id"] for e in timeline] == ["event_001", "event_003", "event_004", "event_016"]
    assert all(e["certainty"] for e in timeline)


def test_session_responses_never_leak_internal_fields(client):
    sid = new_session(client)
    talk(client, sid)
    for suffix in ("", "/history", "/progress", "/progression", "/unlocks", "/clues", "/evidence"):
        body = client.get(f"{API}/sessions/{sid}{suffix}").json()
        assert not (set(all_keys(body)) & FORBIDDEN_KEYS), suffix
    body = talk(client, sid).json()
    assert not (set(all_keys(body)) & FORBIDDEN_KEYS)
