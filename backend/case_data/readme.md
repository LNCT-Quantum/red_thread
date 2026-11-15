
# Case Data

## 1. Purpose

`case_data/<case_id>/` is the authored, case-specific content store.

The Case Engine loads the canonical case records. Progression separately loads `progression.json` and `npc_knowledge.json`.

These files are data, not Python logic.

Current example: `case_data/case_001/` (The Silent Witness).

## 2. Files

| File | Consumer | Contents |
|---|---|---|
| `case.json` | Case Engine | Case metadata and canonical lists of suspect, fact, clue and timeline IDs. |
| `suspects.json` | Case Engine | Suspect profiles and dialogue-relevant characterization. |
| `facts.json` | Case Engine + Progression/LLM context | Canonical facts and entity relationships. |
| `clues.json` | Case Engine + Progression | Evidence records and links to related facts. |
| `timeline.json` | Case Engine | Events and their time/temporal metadata. |
| `progression.json` | Progression | Ordered stages, prerequisites, and clue/fact unlock declarations. |
| `npc_knowledge.json` | Progression | Per-suspect known, unknown and secret facts, notes and clue reaction mappings. |

The Case Engine's required file set is currently the first five files.

The Progression Gate additionally expects valid progression rules and NPC knowledge for the loaded case.

## 3. Record shapes

The exact required fields are enforced by the dataclasses in `shared/contracts/`.

The following is a field-level guide. Check those contract classes before changing the schema.

### `case.json` — one object

Fields:

- `case_id`
- `title`
- `description`
- `victim_id`
- `suspect_ids`
- `fact_ids`
- `clue_ids`
- `timeline_event_ids`
- `schema_version`

The ID arrays are the case's declared membership lists.

Keep them synchronized with the records in the other files.

### `suspects.json` — array of objects

Each record contains:

- `suspect_id`
- `name`
- `occupation`
- `background`
- `public_description`
- `relationship_to_victim`
- `speech_style`
- Optional `age`
- `personality_traits`
- `schema_version`

### `facts.json` — array of objects

Each record contains:

- `fact_id`
- `case_id`
- `statement`
- `category`
- `importance`
- `related_entity_ids`
- `schema_version`

Facts should be atomic, traceable statements.

Do not put dialogue instructions, unlock policy or unsupported interpretation into the canonical fact statement.

### `clues.json` — array of objects

Each record contains:

- `clue_id`
- `case_id`
- `title`
- `description`
- `clue_type`
- `source`
- `related_fact_ids`
- `source_entity_id` (nullable)
- `reliability`
- `schema_version`

`related_fact_ids` must refer to facts in this case.

`reliability` is validated by the `Clue` contract.

A clue's existence does not mean it has been discovered in a particular game.

### `timeline.json` — array of timeline records

Timeline records are parsed as `TimelineEvent` in:

`src/case_engine/timeline.py`

Inspect that class before authoring or changing its fields.

Temporal certainty and ordering are represented separately by:

`src/case_engine/temporal.py`

### `progression.json` — one object

Root shape:

```json
{
  "stages": []
}
```

Each stage supports:

- `stage_id`
- `title`
- `description`
- `required_clue_ids`: clues that must already be discovered before this stage can unlock.
- `required_interviewed_suspect_ids`: suspects whose interviews must be recorded.
- `required_objective_ids`: other objective markers required.
- `unlocks_clue_ids`: clues that become discoverable at this stage.
- `unlocks_fact_ids`: facts that become stage-unlocked at this stage.
- `schema_version` (defaults to `"1.0"` in the runtime rule parser).

Rules:

1. The initial stage must have no requirements.
2. Stage order in the array is meaningful.
3. A later stage cannot be skipped.
4. A clue/fact must not be declared as unlocked by multiple stages.
5. Every referenced ID must exist in the case.
6. Avoid circular or deadlocked requirements.

Example of a deadlock:

A stage requires a clue that is only unlocked by that same stage or a later stage.

### `npc_knowledge.json` — array of per-suspect objects

Each entry contains:

- `suspect_id`
- `known_fact_ids`
- `unknown_fact_ids`
- `secret_fact_ids`
- Optional `knowledge_notes`
- `evidence_reactions`
- `schema_version`

#### Knowledge fields

`known_fact_ids`:

Facts the NPC may know and discuss when those facts are unlocked.

`unknown_fact_ids`:

Facts explicitly outside the NPC's knowledge. They must not be supplied to that NPC.

`secret_fact_ids`:

Facts the NPC knows but conceals. They are only eligible for dialogue context once unlocked and authorized.

Unlisted facts are not automatically known.

The authorization service only permits the suspect's explicitly permitted known/secret facts.

#### Evidence reactions

`evidence_reactions` contains mappings from a presented clue to the suspect's reaction and permitted reveal/conceal behavior.

Each reaction may include:

- `clue_id`
- `reaction_type`
- `emotional_response`
- `reveals_fact_ids`
- `conceals_fact_ids`
- `stated_position`
- `limits`
- `statement_change`
- `alters_alibi`
- `required_stage_id`
- `repeatable`

The runtime validates suspect IDs, clue IDs, fact IDs and required stages.

Keep reaction claims within the canonical case source.

The LLM must not expand `limits` into invented facts.

## 4. Important distinctions

1. **Case record vs player discovery:** A clue in `clues.json` exists in the case; it is not necessarily discovered by a player.
2. **Fact relationship vs fact authorization:** A clue may relate to a fact, but the fact is not automatically authorized for every NPC.
3. **Known vs unlocked:** NPC knowledge says who may know a fact; progression rules say when a stage-gated fact becomes available. Both checks apply.
4. **Secret vs unknown:** A secret is known-but-concealed; unknown means the NPC must not claim knowledge.
5. **Authored stage order:** The order of `stages` is the progression order. Do not sort stages alphabetically.

## 5. Adding a new case

1. Create `case_data/<new_case_id>/`.
2. Author `case.json` and all five Case Engine files: suspects, facts, clues and timeline.
3. Ensure every ID referenced in `case.json` matches exactly one record and every cross-reference resolves.
4. Author `progression.json`; define a reachable initial stage and non-deadlocking prerequisites.
5. Author `npc_knowledge.json` with one entry for every suspect in the case.
6. Be explicit about known, unknown and secret facts.
7. Add evidence reactions only when the case narrative supports the reaction.
8. Define strict reaction limits to prevent invention.
9. Load with `CaseEngine.load(new_case_id)`.
10. Build `ProgressionGate.from_engine(engine)` to exercise both validation paths.
11. Add tests for data loading, stage unlocks, NPC authorization and clue confrontation behavior.

## 6. Authoring and review checklist

- [ ] IDs are unique, stable and consistently referenced.
- [ ] `case.json` ID lists match the record arrays.
- [ ] No unknown JSON fields or duplicate object keys.
- [ ] Every clue-to-fact, fact-to-entity, stage-to-clue/fact/suspect and reaction reference resolves.
- [ ] Initial stage has no prerequisites.
- [ ] Later stages are reachable in order.
- [ ] Each suspect has an NPC knowledge entry.
- [ ] Unknown facts are not accidentally placed in known/secret lists.
- [ ] Reactions do not reveal facts outside the suspect's knowledge or stage authorization.
- [ ] New schema fields are implemented in shared contracts and loaders before data starts using them.
