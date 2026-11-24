from __future__ import annotations

import threading

from .conftest import (
    API, FakeLLMEngine, discover, play_to_stage_4, err, fact_ids_in, json_reply, ok, new_session, talk, SAFE_REPLY,
)


def test_dialogue_success_and_history(client, llm):
    sid = new_session(client)
    response = talk(client, sid, "suspect_002", "Where were you that evening?")
    data = ok(response)
    assert data["npc_id"] == "suspect_002" and data["npc_response"] == SAFE_REPLY
    assert data["is_fallback"] is False
    assert data["turn"]["turn_number"] == 1 and data["turn"]["conversation_id"] == "dlg_suspect_002"
    assert data["turn"]["turn_id"] == "dlg_suspect_002:1"
    assert data["newly_collectable_clues"] == [] and data["newly_unlocked_stages"] == []
    assert data["revision"] == data["state"]["revision"] > 0
    assert llm.calls == 1

    history = ok(client.get(f"{API}/sessions/{sid}/history"))["messages"]
    assert [(m["speaker_type"], m["content"]) for m in history] == [
        ("player", "Where were you that evening?"), ("suspect", SAFE_REPLY)
    ]
    assert [m["sequence_number"] for m in history] == [1, 2]
    assert history[0]["message_id"] == data["turn"]["player_message_id"]
    assert history[1]["message_id"] == data["turn"]["npc_message_id"]
    assert ok(client.get(f"{API}/sessions/{sid}"))["revision"] == data["revision"]


def test_second_turn_increments_turn_number(client):
    sid = new_session(client)
    talk(client, sid)
    assert ok(talk(client, sid, message="And then?"))["turn"]["turn_number"] == 2


def test_response_never_contains_prompt_or_internals(client, llm):
    sid = new_session(client)
    response = talk(client, sid)
    text = response.text
    assert llm.prompts and llm.prompts[0][:200] not in text
    for word in ("prompt", "cited_fact_ids", "model_id", "fake-model", "authorized"):
        assert word not in text


def test_prompt_only_contains_facts_the_progression_gate_authorizes(client, runtime, llm):
    sid = new_session(client)
    talk(client, sid, "suspect_001")
    state = runtime.manager.get_game_state(sid)
    allowed = {
        f for f in runtime.gate.authorization.unlocked_fact_ids(state)
    }
    in_prompt = fact_ids_in(llm.prompts[-1])
    assert in_prompt <= allowed
    secret = {f for f in ("fact_019", "fact_022")}
    assert not (in_prompt & secret)
    hidden = [f.statement for f in runtime.engine.list_facts() if f.fact_id not in allowed]
    assert not any(h in llm.prompts[-1] for h in hidden)


def test_validation_errors(client):
    sid = new_session(client)
    err(talk(client, sid, "ghost"), 404, "NPC_NOT_FOUND")
    err(talk(client, sid, message=""), 422, "REQUEST_VALIDATION_ERROR")
    err(talk(client, sid, message="   "), 422, "REQUEST_VALIDATION_ERROR")
    err(talk(client, sid, message="x" * 5000), 422, "REQUEST_VALIDATION_ERROR")
    err(client.post(f"{API}/sessions/{sid}/dialogue", json={"message": "hi"}), 422, "REQUEST_VALIDATION_ERROR")
    err(client.post(f"{API}/sessions/{sid}/dialogue", json={"npc_id": "suspect_001", "message": "hi", "x": 1}), 422, "REQUEST_VALIDATION_ERROR")
    err(talk(client, sid, presented_clue_ids=["clue_001", "clue_001"]), 422, "REQUEST_VALIDATION_ERROR")
    err(client.post(f"{API}/sessions/{sid}/dialogue", content="{bad", headers={"content-type": "application/json"}), 400, "INVALID_JSON")
    assert ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 0


def test_presenting_clues_is_authorized(client):
    sid = new_session(client)
    err(talk(client, sid, presented_clue_ids=["clue_999"]), 404, "CLUE_NOT_FOUND")
    err(talk(client, sid, presented_clue_ids=["clue_001"]), 403, "CLUE_NOT_DISCOVERED")
    ok(discover(client, sid, "clue_001"))
    assert ok(talk(client, sid, presented_clue_ids=["clue_001"]))["npc_response"]


def test_stale_expected_revision_is_a_conflict_and_nothing_is_stored(client, llm):
    sid = new_session(client)
    ok(discover(client, sid, "clue_001"))
    err(talk(client, sid, expected_revision=0), 409, "REVISION_CONFLICT")
    assert llm.calls == 0 and ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 0
    assert ok(talk(client, sid, expected_revision=1))


def test_llm_unavailable_is_503_and_state_untouched(make_client):
    engine = FakeLLMEngine(healthy=False)
    client = make_client(engine)
    sid = new_session(client)
    err(talk(client, sid), 503, "LLM_UNAVAILABLE")
    assert engine.calls == 0
    assert ok(client.get(f"{API}/sessions/{sid}"))["revision"] == 0
    assert ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 0


def test_llm_timeout_is_503_and_state_untouched(make_client):
    client = make_client(FakeLLMEngine(delay=1.0), dialogue_timeout_s=0.2)
    sid = new_session(client)
    err(talk(client, sid), 503, "LLM_TIMEOUT")
    assert ok(client.get(f"{API}/sessions/{sid}"))["revision"] == 0
    assert ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 0


def test_invalid_model_output_uses_fallback_and_is_flagged(make_client):
    client = make_client(FakeLLMEngine(responder=lambda p: json_reply("As an AI language model I cannot help.")))
    sid = new_session(client)
    data = ok(talk(client, sid))
    assert data["is_fallback"] is True and data["npc_response"]
    assert ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 2
    assert "AI language model" not in data["npc_response"]


def _markers(client, sid):
    runtime = client.app.state.container.registry.get("case_001")
    state = runtime.manager.get_game_state(sid)
    return [m for m in state.completed_objective_ids if "clue_015" in m]


def test_valid_turn_records_the_one_time_reaction(client):
    sid = play_to_stage_4(client)
    ok(discover(client, sid, "clue_015"))
    assert _markers(client, sid) == []
    ok(talk(client, sid, "suspect_002", presented_clue_ids=["clue_015"]))
    assert len(_markers(client, sid)) == 1


def test_fallback_turn_does_not_consume_one_time_reactions(make_client):
    engine = FakeLLMEngine()
    client = make_client(engine)
    sid = play_to_stage_4(client)
    ok(discover(client, sid, "clue_015"))
    engine.responder = lambda p: json_reply("As an AI language model I cannot help.")
    assert ok(talk(client, sid, "suspect_002", presented_clue_ids=["clue_015"]))["is_fallback"] is True
    assert _markers(client, sid) == []


def test_model_leaking_hidden_fact_is_rejected_by_existing_validator(make_client):
    engine = FakeLLMEngine()
    client = make_client(engine)
    runtime = client.app.state.container.registry.get("case_001")
    secret = next(f for f in runtime.engine.list_facts() if f.fact_id == "fact_019")
    engine.responder = lambda p: json_reply(secret.statement)
    sid = new_session(client)
    data = ok(talk(client, sid, "suspect_001"))
    assert secret.statement not in data["npc_response"]
    assert data["is_fallback"] is True


def test_second_turn_for_same_session_while_one_is_running_conflicts(make_client):
    engine = FakeLLMEngine()
    engine.release = threading.Event()
    client = make_client(engine)
    sid = new_session(client)
    results = {}
    worker = threading.Thread(target=lambda: results.update(first=talk(client, sid)))
    worker.start()
    assert engine.entered.wait(timeout=5)
    err(talk(client, sid), 409, "DIALOGUE_TURN_IN_PROGRESS")
    other = new_session(client)  # other sessions are unaffected
    assert other != sid
    engine.release.set()
    worker.join(timeout=10)
    ok(results["first"])
    assert ok(client.get(f"{API}/sessions/{sid}/history"))["total"] == 2


def test_sessions_do_not_share_dialogue_history(client):
    a, b = new_session(client), new_session(client)
    talk(client, a, "suspect_003", "secret question A")
    assert "secret question A" not in client.get(f"{API}/sessions/{b}/history").text
