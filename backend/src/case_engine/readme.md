
# Case Engine

## 1. Purpose and responsibility

`src/case_engine/` loads a case's canonical records, validates their consistency, builds indexed lookup structures and exposes a **read-only** API for querying them.

It is the source of truth for what exists in a case.

It does not:
- Manage player progress.
- Decide what an NPC may reveal.
- Call an LLM.
- Persist a game session.

The engine turns the JSON files under `case_data/<case_id>/` into typed contract objects and an immutable `CaseRegistry` snapshot.

## 2. Files and responsibilities

| File | Responsibility |
|---|---|
| `loader.py` | Reads required JSON files, rejects duplicate keys, constructs contract objects and reports malformed data. |
| `engine.py` | `CaseEngine`, immutable registry, indexed lookup and relationship queries. |
| `entities.py` | Entity references and entity-ID classification. |
| `timeline.py` | Typed timeline event record. |
| `temporal.py` | Timestamp interpretation, certainty, ordering relations and optional ordering assumptions. |
| `validation.py` | Cross-record validation and structured validation report. |
| `proposals.py` | Proposed temporal-order assumptions; these are not automatically treated as established facts. |

## 3. Loading a case

```python
from src.case_engine import CaseEngine

engine = CaseEngine.load("case_001")

# Or supply a different case-data root:
# engine = CaseEngine.load("case_001", data_root="./case_data")

case = engine.case
victim_id = engine.victim_id
report = engine.validation_report
```

`CaseEngine.load(case_id="case_001", data_root=None, ordering_assumptions=())` calls the case-data loader, builds indexes and validates the complete case.

`CaseEngine.from_case_data(data, ordering_assumptions=())` builds an engine from an already-loaded `CaseData` object. This is useful for tests and tooling.

The loader requires:

- `case.json`
- `suspects.json`
- `facts.json`
- `clues.json`
- `timeline.json`

Progression and NPC knowledge files are consumed by the Progression module, not by the Case Engine loader.

### Load-time failure behavior

The loader rejects:

- Invalid case IDs.
- Missing directories or files.
- Malformed JSON.
- Duplicate JSON object keys.
- Missing contract fields.
- Unknown fields.
- Invalid record values.

Cross-record validation is available through `validation_report`. Callers should not silently proceed when the report contains errors.

Errors use the shared exception types in `shared/contracts/errors.py`.

## 4. Public API

### Case identity and snapshot

- `engine.case` — typed `Case` record.
- `engine.case_id` — loaded case identifier.
- `engine.victim_id` — victim entity identifier.
- `engine.registry` — immutable `CaseRegistry` containing case, suspects, facts, clues, timeline events and entity references.
- `engine.validation_report` — structured validation result.
- `engine.ordering_assumptions` — assumptions supplied to temporal ordering.

### Direct lookup (raises if missing)

- `get_suspect(suspect_id)`
- `get_fact(fact_id)`
- `get_clue(clue_id)`
- `get_timeline_event(event_id)`
- `get_entity_reference(entity_id)`

These are strict lookups. Do not treat a missing record as an empty result. Handle the relevant `ResourceNotFoundError` or contract exception.

### Listing and relationship queries

- `list_suspects()`
- `list_facts()`
- `list_clues()`
- `list_timeline_events()`
- `list_entity_references()`
- `unregistered_entity_ids()`
- `facts_by_category(category)`
- `facts_by_importance(importance)`
- `clues_by_type(clue_type)`
- `testimony_clues()`
- `clues_for_fact(fact_id)`
- `facts_for_clue(clue_id)`
- `facts_for_suspect(suspect_id)`
- `facts_for_entity(entity_id)`
- `events_for_fact(fact_id)`
- `facts_for_event(event_id)`
- `events_for_entity(entity_id)`
- `clues_sourced_from(entity_id)`
- `temporal_descriptor(event_id)`
- `events_by_certainty(certainty)`
- `compare_events(first_event_id, second_event_id)`
- `unresolved_ordering_pairs()`

The returned records preserve canonical case ordering where documented by the implementation.

Query methods are read-only. They never mark clues as discovered or change player state.

## 5. Data and temporal semantics

A `Fact` is a canonical statement.

A `Clue` is evidence that can be linked to one or more facts.

`related_fact_ids` on a clue and `related_entity_ids` on a fact establish relationships. They do not themselves grant player or NPC authorization.

A `TimelineEvent` may have uncertain timing.

`compare_events` reports the engine's temporal relation and basis rather than inventing a definitive order.

Explicit `OrderingAssumption` values are assumptions and must remain distinguishable from source-established chronology.

`TESTIMONY_CLUE_TYPE` is exported as `"witness_statement"`.

## 6. Boundary with other modules

- Case Engine answers: **What records exist, and how are they related?**
- Progression answers: **What is currently unlocked, and what may this suspect know or react to?**
- Game State answers: **What has this player discovered/interviewed, and what is the current session state?**
- LLM integration answers: **How should the authorized context be rendered into a natural-language response?**

Never use a direct Case Engine lookup as proof that a clue is unlocked or that a suspect is allowed to know a fact.

Those decisions belong to Progression authorization.

## 7. Extension rules

When adding case content:

1. Update the relevant JSON records.
2. Update the top-level ID lists in `case.json`.
3. Keep IDs unique and stable.
4. Validate every referenced clue, fact, suspect and timeline event.
5. Do not add runtime progression policy or player-specific state to this module.
