# Red Thread REST API

Base URL: `http://<host>:<port>/api/v1` (default `http://127.0.0.1:8000/api/v1`).
Interactive OpenAPI docs: `/api/v1/docs` (disable with `API_ENABLE_DOCS=false`).

The frontend only needs to send JSON and read JSON. It never needs to know the Python internals.

---

## 1. Running

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000      # or: python main.py
```

For a browser frontend on another origin, set CORS (nothing is hard-coded):

```bash
API_CORS_ORIGINS=http://localhost:5173 python -m uvicorn main:app --port 8000
```

NPC dialogue needs the local LLM (Ollama by default, see `docs/llm-integration.md`).
Everything except dialogue works without it. `GET /health/ready` reports the LLM state.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `API_CORS_ORIGINS` | *(empty = no CORS headers)* | Comma-separated allowed browser origins (`*` allowed) |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | Used by `python main.py` |
| `API_DIALOGUE_TIMEOUT_S` | `150` | Hard cap on one NPC reply. The LLM engine has its own finer `LLM_*` timeouts |
| `API_LLM_CONCURRENCY` | `2` | Simultaneous LLM generations across all players |
| `API_INTERVIEW_MIN_TURNS` | `1` | NPC replies required before an interview can be completed |
| `API_MAX_BODY_BYTES` | `16384` | Larger request bodies get `413` |
| `API_CASE_IDS` | all cases in `case_data/` | Restrict which cases load |
| `API_CASE_DATA_ROOT` | `backend/case_data` | Case data directory |
| `API_ENABLE_DOCS` | `true` | Serve `/api/v1/docs` |
| `API_LOG_LEVEL` | `INFO` | Python log level |

### Running the tests

```bash
cd backend
python -m pytest tests/api -q                              # API tests (no LLM, no network)
python -m pytest -q --ignore=tests/test_engine_latency.py  # API + existing backend tests
```

`tests/test_engine_latency.py` already failed to import before the API existed
(`from engine_runner import ...` instead of `src.llm.engine_runner`). It is a latency benchmark
that needs a live model, so it is excluded above.

---

## 2. Conventions

### Envelope
Every response (success or failure) has exactly this shape, built from `shared/contracts/api.py`:

```json
{ "request_id": "req_...", "success": true,  "data": { }, "error": null, "schema_version": "1.0" }
{ "request_id": "req_...", "success": false, "data": null,
  "error": { "code": "SESSION_NOT_FOUND", "message": "The requested session does not exist",
             "details": [], "schema_version": "1.0" },
  "schema_version": "1.0" }
```
(`error.schema_version` comes from the existing `APIError` contract.)

### Request IDs
Each response carries `request_id` and the `X-Request-ID` header. A client may send its own
`X-Request-ID` (8-128 chars of `A-Za-z0-9._-`) for tracing; otherwise one is generated.

### Authentication / session assumptions
* **There is no user authentication yet.** A `session_id` (random 128-bit value) acts as a
  bearer capability: whoever holds it can read and play that session. Treat it as a secret.
* Sessions are **in memory**. They are **lost when the backend restarts** and never expire
  automatically. After a restart the old ID returns `404 SESSION_NOT_FOUND`; the frontend must
  start a new session. The repository abstraction is intact, so persistent storage can be added later.
* Sessions are isolated from each other (separate state, history and progress).

### Optimistic concurrency
Every session state carries a `revision`. Mutating calls (`dialogue`, `discover`, `interviews/.../complete`)
accept an optional `expected_revision`. If it differs from the stored revision the call fails with
`409 REVISION_CONFLICT` and **nothing is changed** (for dialogue, the LLM is not even called).

### Information boundary
Responses are built from explicit allow-list models. The API never returns: hidden/secret facts,
NPC knowledge, unrevealed clue text, clue `reliability`, `related_fact_ids`, prompts, LLM metrics,
progression markers or the solution. Details of what is public:

| Endpoint | What is returned |
|---|---|
| suspects | name, age, occupation, public description, relationship (not background / speech style / traits) |
| case `clues` | clues collectable at the start: **title, type, location only** |
| case `facts` | baseline background facts only (7 of 44 in `case_001`) |
| case `timeline` | events whose facts are all public backstory (4 of 16); crime events withheld |
| session `clues` / `evidence` | full description **only for clues the player discovered** |
| progression | current/reached stages, and for the next stage only `requirements_met / requirements_total` |

"Public" is derived from the existing `ProgressionGate` initial-state rules, not a second list.
Case authors must gate any spoiler fact (stage, clue link or NPC secret); un-gated facts count as public.

### Status codes

| HTTP | When |
|---|---|
| 200 / 201 | Success / session created |
| 400 | `INVALID_JSON`, `INVALID_REQUEST` |
| 403 | `CLUE_LOCKED`, `CLUE_NOT_DISCOVERED`, `ACCESS_DENIED` (progression gate said no) |
| 404 | Unknown case/session/NPC/clue/route |
| 405 / 413 | Wrong method / body too large |
| 409 | `REVISION_CONFLICT`, `DIALOGUE_TURN_IN_PROGRESS`, `DIALOGUE_TURN_STALE`, `INTERVIEW_NOT_READY`, `GAME_NOT_ACTIVE` |
| 422 | `REQUEST_VALIDATION_ERROR` (details list `field: reason`) |
| 500 | `INTERNAL_ERROR` (no stack traces, paths or internals are ever returned) |
| 503 | `NOT_READY`, `LLM_UNAVAILABLE`, `LLM_TIMEOUT`, `LLM_NOT_CONFIGURED` |

`403` is used (not in the original list) because "not allowed yet" is neither a missing resource nor a state conflict.

### Error codes
`SESSION_NOT_FOUND`, `CASE_NOT_FOUND`, `NPC_NOT_FOUND`, `CLUE_NOT_FOUND`, `ROUTE_NOT_FOUND`,
`METHOD_NOT_ALLOWED`, `CLUE_LOCKED`, `CLUE_NOT_DISCOVERED`, `ACCESS_DENIED`, `REVISION_CONFLICT`,
`DIALOGUE_TURN_IN_PROGRESS`, `DIALOGUE_TURN_STALE`, `INTERVIEW_NOT_READY`, `GAME_NOT_ACTIVE`,
`STATE_CONFLICT`, `INVALID_JSON`, `INVALID_REQUEST`, `REQUEST_VALIDATION_ERROR`, `PAYLOAD_TOO_LARGE`,
`NOT_READY`, `LLM_UNAVAILABLE`, `LLM_TIMEOUT`, `LLM_NOT_CONFIGURED`, `SESSION_STATE_INVALID`, `INTERNAL_ERROR`.

---

## 3. Endpoints

`BASE=http://127.0.0.1:8000/api/v1`. All examples below are real output from the running server
(long strings shortened where marked).

### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness. Always 200 while the process is up |
| GET | `/health/ready` | 200 if case data, progression, session store **and LLM** are ready, else 503 `NOT_READY` with the failing components in `error.details` |

```bash
curl $BASE/health
# {"request_id":"req_...","success":true,"data":{"status":"ok","service":"red-thread-backend","version":"1.0.0","uptime_seconds":2.6},"error":null,"schema_version":"1.0"}
curl $BASE/health/ready
# data: {"ready":true,"components":{"case_data":{"status":"ok","detail":"1 case(s) loaded"},"progression":{...},"session_store":{"status":"ok","detail":"in-memory (sessions are lost when the backend restarts)"},"llm":{"status":"ok"}}}
# LLM down -> 503 {"error":{"code":"NOT_READY","details":["llm: unavailable (model server unreachable)"]}}
```

### Cases (no session needed)

| Method | Path | `data` |
|---|---|---|
| GET | `/cases` | `{items:[{case_id,title,playable}], count}` |
| GET | `/cases/{case_id}` | `{case_id,title,playable,description,suspect_count}` |
| GET | `/cases/{case_id}/suspects` | `{items:[{suspect_id,name,age,occupation,public_description,relationship_to_victim}],count}` |
| GET | `/cases/{case_id}/clues` | `{items:[{clue_id,title,clue_type,source}],count}`: start-of-case clues, no descriptions |
| GET | `/cases/{case_id}/facts` | `{items:[{fact_id,statement,category}],count}`: public background only |
| GET | `/cases/{case_id}/timeline` | `{items:[{event_id,time_text,certainty,description,involved_suspect_ids}],count}`: backstory only; declared order, **not** a verified chronology |

```bash
curl $BASE/cases/case_001
# "data": {"case_id":"case_001","title":"The Silent Witness","playable":true,"description":"Dr. Rishabh Malhotra, ...","suspect_count":3}
curl $BASE/cases/case_001/clues
# "items":[{"clue_id":"clue_001","title":"The Chessboard","clue_type":"physical_evidence","source":"Victim's study, between the two chairs"}, ...]
```
Errors: unknown case → `404 CASE_NOT_FOUND`.

### Sessions

| Method | Path | Body | Result |
|---|---|---|---|
| POST | `/sessions` | `{"case_id":"case_001"}` | **201**, `Location` header, `{session_id, state}` |
| GET | `/sessions/{id}` | | session state |
| DELETE | `/sessions/{id}` | | `{session_id, deleted:true}`: removes session and history (the existing semantics are delete) |
| GET | `/sessions/{id}/history?npc_id=&limit=100&offset=0` | | messages + per-NPC conversation summaries |
| GET | `/sessions/{id}/progress` | | stage, clue counts, interviews, conversations, discovered clue summaries |

No player data is collected or stored: `GameState` has no such field, and unknown body fields are rejected with 422.

Session `state`:
```json
{ "session_id": "e03d12ca...", "case_id": "case_001", "status": "active", "revision": 0,
  "stage": {"stage_id":"stage_1","title":"Initial Investigation","description":"...","index":1},
  "total_stages": 5, "discovered_clue_ids": [], "interviewed_suspect_ids": [], "current_suspect_id": null }
```
```bash
curl -X POST $BASE/sessions -H 'Content-Type: application/json' -d '{"case_id":"case_001"}'
curl $BASE/sessions/$SID/history?npc_id=suspect_001
curl -X DELETE $BASE/sessions/$SID
```
History message: `{message_id, conversation_id, npc_id, speaker_type: player|suspect, speaker_id, content, sequence_number, turn_number, created_at}`.
(`conversation_id` is the dialogue-session ID, one per NPC; it is *not* the session ID.)

### NPC dialogue

`POST /sessions/{id}/dialogue`

```json
{ "npc_id": "suspect_002", "message": "Where were you last night?",
  "presented_clue_ids": [], "expected_revision": 0 }
```
`message`: 1-500 characters (the prompt builder's limit). `presented_clue_ids` (optional, max 10) must be clues the
player has already discovered. `expected_revision` optional.

Flow (all existing modules): validate session/NPC/clues → `GameStateManager.prepare_dialogue_turn` (the
`ProgressionGate` chooses facts and evidence reactions) → `DialoguePipeline.generate` (prompt, LLM, parse,
leak/format validation, retry, fallback) → `complete_dialogue_turn` (re-validates, records one-time reactions)
→ both messages appended to history.

```json
{ "npc_id":"suspect_002", "npc_response":"I was at the gallery all evening, detective. Ask anyone.",
  "turn":{"turn_id":"dlg_suspect_002:1","turn_number":1,"conversation_id":"dlg_suspect_002",
          "player_message_id":"msg_...","npc_message_id":"msg_..."},
  "is_fallback": false, "response_time_ms": 5,
  "newly_unlocked_stages": [], "newly_collectable_clues": [],
  "revision": 2, "state": { } }
```
* `is_fallback: true` means the model could not produce a valid in-character answer (e.g. it tried to leak a
  hidden fact) and the pipeline's safe deflection line was used. It is stored in history, but it does **not**
  consume one-time evidence reactions, so the player can present the evidence again.
* One turn per session at a time: a second concurrent request gets `409 DIALOGUE_TURN_IN_PROGRESS`.
* LLM unreachable → `503 LLM_UNAVAILABLE`; exceeded `API_DIALOGUE_TIMEOUT_S` → `503 LLM_TIMEOUT`. In both cases
  nothing is stored and the revision is unchanged, so the client can simply retry.
* Set a generous client timeout (the first request after a model load can take over a minute).

### Clues and evidence

| Method | Path | Result |
|---|---|---|
| GET | `/sessions/{id}/clues` | `{discovered_count,total_count,clues:[{clue_id,title,clue_type,source,description}]}` |
| POST | `/sessions/{id}/clues/{clue_id}/discover` | body optional `{"expected_revision":n}` |
| GET | `/sessions/{id}/evidence` | `{collected:[full clues], collectable:[{clue_id,title,clue_type,source}]}` |

`discover` is authorized by the progression gate: a locked clue returns `403 CLUE_LOCKED` (no detail about why),
an unknown one `404 CLUE_NOT_FOUND`. Re-discovering is a no-op (`already_discovered:true`). The result lists
`newly_unlocked_stages` and `newly_collectable_clues` caused by the discovery. Which clues are *unlocked*
comes from stage progress and completed interviews; the backend has no separate "search the room" mechanic,
so `collectable` is exactly what a player may discover now.

```bash
curl -X POST $BASE/sessions/$SID/clues/clue_005/discover
# 403 {"error":{"code":"CLUE_LOCKED","message":"This clue is not available yet","details":[]}}
curl -X POST $BASE/sessions/$SID/clues/clue_001/discover
```

### Progression

| Method | Path | Result |
|---|---|---|
| GET | `/sessions/{id}/progression` | `current_stage`, `unlocked_stages`, `total_stages`, `is_final_stage`, `next_stage:{requirements_total,requirements_met}` |
| GET | `/sessions/{id}/unlocks` | current stage, reached stage IDs, `collectable_clues`, discovered clue IDs, completed interviews |
| POST | `/sessions/{id}/interviews/{suspect_id}/complete` | `{suspect_id, already_completed, newly_unlocked_stages, newly_collectable_clues, state}` |

There is **no** endpoint that sets a stage or unlocks anything directly; stages advance only inside the progression
gate after clue discoveries and interviews.

**Added endpoint: interview completion.** The existing code records an interview only when "called explicitly"
and never defines when one counts as complete, yet stage 3 and the testimony clues depend on it. The API therefore
exposes this call, guarded by one rule of its own: the suspect must have answered the player at least
`API_INTERVIEW_MIN_TURNS` times in this session, otherwise `409 INTERVIEW_NOT_READY`. The threshold is a
game-design decision for the team; change it by env var, or replace this with automatic completion later.

---

## 4. Frontend integration guide

Recommended order (`api` = a tiny wrapper that unwraps the envelope and throws on `success:false`):

```js
const BASE = import.meta.env.VITE_API_BASE_URL;   // e.g. "http://127.0.0.1:8000/api/v1"; configure, don't hard-code

async function api(path, { method = "GET", body, timeoutMs = 20000 } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const env = await res.json();
  if (!env.success) throw Object.assign(new Error(env.error.message), env.error, { status: res.status, requestId: env.request_id });
  return env.data;
}
```

1. **Check health**: `await api("/health")`; optionally `/health/ready` (503 `NOT_READY` ⇒ show "backend starting"; check `details` for `llm`).
2. **Load cases**: `const { items } = await api("/cases")`.
3. **Load case info**: `api("/cases/case_001")`, `.../suspects`, `.../clues`, `.../facts`, `.../timeline` in parallel.
4. **Create session**: `const { session_id, state } = await api("/sessions", { method: "POST", body: { case_id } })`; store `session_id` (e.g. `localStorage`).
5. **Retrieve initial state**: `state` is in the create response; or `api(`/sessions/${session_id}`)`.
6. **Talk to an NPC**:
   ```js
   const turn = await api(`/sessions/${sid}/dialogue`,
     { method: "POST", timeoutMs: 180000, body: { npc_id: "suspect_001", message, expected_revision: state.revision } });
   state = turn.state;                       // already updated, no refetch needed
   show(turn.npc_response);
   turn.newly_collectable_clues.forEach(notify);
   ```
   Handle `409 REVISION_CONFLICT` (refetch state, retry), `409 DIALOGUE_TURN_IN_PROGRESS` (disable the send button while a request is pending), `503 LLM_*` (offer retry; nothing was stored).
7. **Discover / show clues**: `api(`/sessions/${sid}/evidence`)` for the board (`collected` + `collectable`);
   `api(`/sessions/${sid}/clues/${id}/discover`, { method: "POST" })` when the player collects one (handle `403 CLUE_LOCKED`).
   After a suspect has answered, `POST .../interviews/{suspect_id}/complete` when your UI ends the interview.
8. **Refresh after actions**: every mutating response contains the new `state` (with `revision`). Use `GET /sessions/{id}/progress`
   or `/progression` for HUD data.
9. **Resume**: on load, read the stored `session_id`; `GET /sessions/{id}`. On `404 SESSION_NOT_FOUND` (deleted or backend restarted)
   clear it and go to step 4. Rebuild chat from `GET /sessions/{id}/history`.

CORS: start the backend with `API_CORS_ORIGINS=<your frontend origin>`. The `X-Request-ID` response header is exposed to the browser.

---

## 5. Architecture

```
backend/
  main.py                      app = create_app(); python main.py -> uvicorn
  api/
    app.py                     app factory: middleware, CORS, handlers, router
    config.py                  Settings from env (API_*)
    envelope.py                APIResponse/APIError (shared contracts) + JSON serialization
    errors.py                  ApiError, domain-error -> safe HTTP error translation
    middleware.py              request IDs, body-size guard, safe access log, last-resort 500
    dependencies.py            AppContainer + injected services
    presenters.py              domain objects -> public models (the allow-list decisions)
    routes/                    health, cases, suspects, timeline, clues, sessions, dialogue, progression
    schemas/                   requests.py (validation), responses.py (public models)
    services/                  runtime (per-case wiring), case_service, game_service,
                               dialogue_service, system_service, guards, llm_gateway
  tests/api/                   73 tests (scripted fake LLM engine, no network)
```

| Endpoint group | Existing module used |
|---|---|
| cases, suspects, clues, facts, timeline | `CaseEngine`; public subset from `ProgressionGate.authorization` initial state |
| sessions, history | `GameStateManager` + `InMemoryGameStateRepository` |
| discover clue | `GameStateManager.discover_clue` → `ProgressionGate` (`require_clue_discoverable`) |
| interview complete | `GameStateManager.record_interview` → stage evaluation in `ProgressionGate` |
| dialogue | `prepare_dialogue_turn` → `DialoguePipeline` (`LLMAdapter`, `LocalLLMEngine`) → `complete_dialogue_turn` → `append_dialogue_message` |
| progression, unlocks, progress | `ProgressionGate.manager`, `authorization`, `progression_rules` |
| health/ready | case runtimes + `LocalLLMEngine.check_health` |

## 6. Known limitations / gaps

* **In-memory sessions**: lost on restart, never expire, memory grows with sessions. Single process only: the per-session
  guards are in-process (the repository's revision check still protects state, but run **one** uvicorn worker).
* **No authentication**; the session ID is the only credential.
* **One case exists** (`case_001`). Several cases are supported (each gets its own store) but untested with real data.
* **No session-aware timeline or facts.** The data has no notion of "facts the player knows" (unlocked facts are what an NPC
  *may* say, including secrets), so exposing them would leak the solution. Only public backstory is returned.
* **No accusation / game-over endpoint**: no such logic exists in the backend. Sessions are never marked `completed`.
* **No idempotency keys**: retrying a POST dialogue after a lost response may create a second turn.
* **Epistemic Engine** (`src/progression/epistemic_engine.py`) is not connected to dialogue anywhere in the repository, so it is not used here.
* Request-size guard relies on `Content-Length`; put a reverse proxy in front for chunked uploads in production.
* `current_suspect_id` is never updated by the API (always `null`); the client tracks the active NPC.
* Pre-existing: `tests/test_engine_latency.py` cannot be imported (see section 1).
