
# Game State Management

## 1. Purpose

`src/game_state/` owns:

- Game-session lifecycle.
- Persisted player progress.
- Dialogue history.
- Validated state transitions.

It coordinates the Case Engine and optional Progression Gate, but it does not define case content or independently implement progression/authorization policy.

## 2. Files and types

| File | Main types | Responsibility |
|---|---|---|
| `state_manager.py` | `GameStateManager`, `StateChange` | Public session API, validation, transitions, dialogue preparation/completion and revision handling. |
| `state_repository.py` | `GameSession`, `GameStateRepository`, `InMemoryGameStateRepository` | Storage abstraction and in-memory implementation. |
| `__init__.py` | Public exports/constants | Stable module import surface. |

`GameSession` contains a `GameState` plus immutable dialogue-history tuple.

`GameStateRepository` defines:

- `create`
- `get`
- `save(session, expected_revision)`
- `delete`

`InMemoryGameStateRepository` is the provided in-memory implementation. It is not durable across process restarts.

## 3. Initialization

```python
from src.case_engine import CaseEngine
from src.progression import ProgressionGate
from src.game_state import GameStateManager, InMemoryGameStateRepository

engine = CaseEngine.load("case_001")
gate = ProgressionGate.from_engine(engine)
repository = InMemoryGameStateRepository()

games = GameStateManager(engine, repository, gate)

state = games.create_game_session()

# Or supply a stable game_id:
# state = games.create_game_session(game_id="game_abc")
```

A supplied progression gate must have been built on the exact same `CaseEngine` instance.

A manager without a gate can create/read/update basic sessions, but dialogue request preparation and clue authorization/completion paths that require progression are unavailable.

## 4. GameState model

The shared contract fields are:

- `game_id`
- `case_id`
- `discovered_clue_ids`
- `interviewed_suspect_ids`
- `completed_objective_ids`
- `dialogue_session_ids`
- `current_suspect_id`
- `status` (default `active`)
- `revision` (starts at `0`)
- `schema_version`

State is immutable.

Methods return a new state or `StateChange`. Do not mutate internal values or directly edit progress arrays.

Stage markers and one-time reaction markers are backend-owned entries in `completed_objective_ids`.

## 5. Public API

### Session lifecycle

- `create_game_session(case_id=None, game_id=None)` — creates a fresh session for the manager's loaded case.
- `get_game_state(game_id)` — returns immutable current state.
- `get_current_stage_id(game_id)` — returns stage ID when a gate is configured, otherwise `None`.
- `delete_game_session(game_id)` — deletes session.

### Dialogue history

- `get_dialogue_history(game_id)` — complete history, oldest first.
- `get_recent_dialogue_history(game_id, dialogue_session_id, max_turns=5)` — bounded history for one conversation. A turn is a player message plus a suspect reply; default is 5 turns, maximum is 10.
- `append_dialogue_message(game_id, message, expected_revision=None)` — validates and appends a `DialogueMessage`.

Message IDs are idempotent if the exact same message is re-sent.

Conflicting duplicate IDs and out-of-order sequence numbers are rejected.

### LLM dialogue orchestration

- `build_dialogue_request(game_id, *, request_id, suspect_id, player_message, dialogue_session_id, presented_clue_ids=(), max_turns=5)` — creates a `DialogueRequest` using recent stored history and Progression authorization.
- `prepare_dialogue_turn(...)` — returns `PreparedDialogueTurn` containing the request plus resolved evidence reactions.
- `complete_dialogue_turn(game_id, turn, draft, expected_revision=None)` — validates the draft against the prepared request, revalidates the request against current state, recomputes evidence reactions and rejects stale/forged turns.

Important:

`complete_dialogue_turn` records newly delivered one-time reaction markers.

It does **not** itself append the player and assistant `DialogueMessage` records.

Use `append_dialogue_message` for history persistence.

### Investigation mutations

- `discover_clue(game_id, clue_id, expected_revision=None)` — validates the clue and (when gate configured) verifies it is discoverable; evaluates progression and commits once.
- `record_interview(game_id, suspect_id, expected_revision=None)` — records a completed interview. Merely opening a conversation is not an interview completion.
- `update_game_state(game_id, current_suspect_id=UNSET, status=UNSET, expected_revision=None)` — only these freely settable fields are supported. Progress collections/stage markers must use dedicated operations.
- `increment_revision(game_id, expected_revision=None)` — explicit standalone revision increment.

`StateChange` contains:

- `state`
- `changed`
- `newly_unlocked_stage_ids`

## 6. State transition and concurrency model

Mutations are computed from immutable values and saved as one logical transition.

A successful state change increments revision exactly once.

Idempotent no-ops and failures do not increment it.

The manager uses a re-entrant lock for in-process coordination.

The repository's `save` also checks an expected revision, so stale writes raise `StateConflictError` (`REVISION_CONFLICT`).

Pass the revision observed by the caller as `expected_revision` when coordinating concurrent clients.

This is optimistic concurrency control, not a distributed database guarantee.

A production multi-process deployment needs a durable repository implementation with an atomic compare-and-swap/transaction around revision checking and saving.

## 7. Recommended LLM turn sequence

1. Read current `GameState` and revision.
2. Call `prepare_dialogue_turn(...)` with game ID, request ID, target suspect, player text, dialogue session ID and presented clue IDs.
3. Give the LLM the `DialogueRequest` plus the resolved reaction context.
4. Do not add unauthorized facts or fetch all facts and let the model choose.
5. Parse the model result as `DialogueDraft`.
6. Validate citations and identity against the request.
7. Call `complete_dialogue_turn(...)` with the prepared turn and draft.
8. If the state changed since preparation, handle the stale-turn conflict and prepare a new turn rather than forcing the old result.
9. Persist the player and suspect messages using `append_dialogue_message(...)`.
10. Use unique message IDs and strictly increasing sequence numbers per dialogue session.

The exact orchestration layer may batch these operations into a service transaction later, but the current public methods should not be bypassed.

## 8. Important integration constraints

- Do not directly edit `GameState` fields or repository internals.
- Do not mark an interview complete merely because a dialogue request was sent.
- Do not record a clue before the backend authorizes discovery.
- Do not let the frontend or LLM write stage markers or reaction markers.
- Keep `dialogue_session_id` distinct from `game_id`; one game can have multiple dialogue sessions.
- Store the complete history; use bounded recent history only as LLM context.
- Handle inactive games and stale revisions as explicit errors.

## 9. Production persistence

`InMemoryGameStateRepository` is a reference/test implementation.

To use a database, implement `GameStateRepository` with atomic:

- `create`
- `get`
- `save`
- `delete`

Persist both the `GameState` and ordered `DialogueMessage` history.

`save` must enforce `expected_revision` atomically; otherwise two workers can overwrite each other's progress.
