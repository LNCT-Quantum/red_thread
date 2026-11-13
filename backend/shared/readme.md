
# Shared Contracts

## 1. Purpose

`shared/contracts/` defines the typed, validated data structures exchanged across backend modules.

Treat these classes as the backend's interface/ABI at the Python-object level.

The LLM integration team should consume and return these contracts instead of inventing parallel dictionaries or private schemas.

Contracts validate their own fields in `__post_init__`.

They are generally frozen dataclasses. Construct new values rather than mutating existing instances.

## 2. Contract inventory

| File | Main types | Used for |
|---|---|---|
| `case.py` | `Case` | Case identity and canonical membership ID lists. |
| `suspect.py` | `Suspect` | Suspect profile and characterization. |
| `fact.py` | `Fact` | Canonical fact statement and related entities. |
| `clue.py` | `Clue` | Evidence metadata and fact links. |
| `game_state.py` | `GameState` | Immutable per-game progress snapshot. |
| `progression.py` | `ProgressionStage`, `Progression` | Basic typed progression document representation. |
| `dialogue.py` | `DialogueMessage`, `GenerationLimits`, `DialogueRequest`, `GenerationMetrics`, `DialogueDraft` | Conversation history and LLM request/response boundary. |
| `api.py` | `APIError`, `APIResponse` | API response envelope. |
| `errors.py` | `RedThreadError`, `ContractValidationError`, `ResourceNotFoundError`, `PermissionDeniedError`, `StateConflictError`, `ExternalServiceError` | Typed failures. |

Important:

`shared.contracts.progression.Progression` is a data contract, while runtime progression evaluation uses `src.progression.progression_rules.ProgressionRules` and `StageRule`.

Do not assume these classes are interchangeable.

## 3. Core fields

### GameState

Fields:

- `game_id`
- `case_id`
- `discovered_clue_ids`
- `interviewed_suspect_ids`
- `completed_objective_ids`
- `dialogue_session_ids`
- `current_suspect_id`
- `status`
- `revision`
- `schema_version`

The current state is immutable.

`revision` is a concurrency/version counter.

`completed_objective_ids` also stores backend-reserved markers such as:

- `stage:<stage_id>`
- `reaction:<suspect_id>:<clue_id>`

Clients must not fabricate or edit these markers.

### Dialogue request/response boundary

#### DialogueRequest

Fields:

- `request_id`
- `case_id`
- `suspect_id`
- `player_message`
- `authorized_fact_ids`
- `presented_clue_ids`
- `dialogue_history`
- `generation_limits`
- `schema_version`

`authorized_fact_ids` are computed by the backend only.

`presented_clue_ids` are clues the player is presenting in this turn and which have passed backend checks.

`dialogue_history` is a typed `DialogueMessage` sequence.

`generation_limits` contains:

- `max_tokens`
- `temperature`
- `top_p`

#### DialogueDraft

Fields:

- `request_id`
- `suspect_id`
- `content`
- `cited_fact_ids`
- `cited_clue_ids`
- `metrics`
- `schema_version`

`metrics` is a `GenerationMetrics` object containing:

- `model_id`
- `time_to_first_token_ms`
- `generation_time_ms`
- `prompt_tokens`
- Optional `completion_tokens`

`DialogueDraft.validate_against_request(request)` checks request identity and that cited facts/clues belong to the request's authorized/presented sets.

The LLM must not create a different request ID or suspect ID.

### DialogueMessage

`DialogueMessage` is the persisted chat-history record.

It includes:

- `message_id`
- `session_id`
- `case_id`
- `speaker_type`
- Optional `speaker_id`
- `content`
- `sequence_number`
- `created_at`
- `schema_version`

## 4. Serialization

`DialogueRequest` and `DialogueDraft` provide:

- `to_dict()`
- `to_json()`
- `from_dict()`
- `from_json()`

`GenerationLimits` and `GenerationMetrics` provide:

- `to_dict()`
- `from_dict()`

Use these methods at JSON boundaries rather than hand-writing serializers.

The parsers validate object shape and reject duplicate JSON keys.

`DialogueMessage` and history have internal serialization helpers used by the state repository.

Use the repository's public APIs rather than reaching into those helpers.

## 5. Error types

| Exception | Meaning / typical cause |
|---|---|
| `ContractValidationError` | Invalid field, malformed contract or cross-module contract mismatch. |
| `ResourceNotFoundError` | Unknown game/case/suspect/clue or missing resource. |
| `PermissionDeniedError` | Operation is not allowed by progression/authorization policy. |
| `StateConflictError` | Stale revision, invalid transition, inactive game or stale prepared turn. |
| `ExternalServiceError` | Failure at an external dependency boundary. |

Catch typed errors at service/API boundaries.

Do not convert authorization failures into a normal LLM prompt or silently drop them.

## 6. LLM integration rules

1. The backend creates `DialogueRequest`.
2. The model must never choose or expand `authorized_fact_ids`.
3. The model returns content and citations in the `DialogueDraft` shape.
4. `cited_fact_ids` must be a subset of `authorized_fact_ids`.
5. `cited_clue_ids` must be a subset of `presented_clue_ids`.
6. Preserve `request_id` and `suspect_id` exactly.
7. Use `DialogueDraft.from_json()` or `from_dict()` to parse model output.
8. Call `validate_against_request()` after parsing.
9. The state manager also validates at completion.
10. Do not persist raw unvalidated model JSON as a trusted draft.

## 7. Adding or changing a contract

1. Update the dataclass and its validation in the relevant module.
2. Update serialization/deserialization where applicable.
3. Update all producers and consumers in the same change.
4. Update the module README and any API/LLM schema docs.
5. Add positive and negative tests, including malformed values and unauthorized citations.
6. Coordinate schema-version compatibility before changing persisted or network-visible shapes.
