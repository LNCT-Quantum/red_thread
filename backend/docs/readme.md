
# Backend Module Documentation

This folder contains the module-level technical guides for the Red Thread backend.

Start with the integration guide, then use the individual README for the module you are implementing against.

## Module guides

1. [Case Engine](case-engine/README.md) — canonical, validated, read-only case data and lookup APIs.
2. [Case Data](case-data/README.md) — JSON files, schemas, ID relationships and authoring rules for a case.
3. [Shared Contracts](shared-contracts/README.md) — typed interfaces and validation exchanged between modules and the LLM subsystem.
4. [Progression](progression/README.md) — stage evaluation, clue/fact unlocks, NPC knowledge, evidence reactions and dialogue authorization.
5. [Game State](game-state/README.md) — game sessions, revisions, dialogue history and state transitions.
6. [LLM Integration Guide](llm-integration.md) — end-to-end request/response flow and integration responsibilities.

## Source of truth

These guides describe the implementation in:

- `backend/src/`
- `backend/shared/contracts/`
- `backend/case_data/`

If code changes, update the relevant guide in the same pull request.

Examples are illustrative; the Python signatures and dataclass definitions in source remain authoritative.

## Import conventions

Run commands from the `backend/` directory.

Existing source imports use both `shared.contracts...` and `src....`; preserve the repository's established import style.

Typical imports:

```python
from src.case_engine import CaseEngine
from src.progression import ProgressionGate
from src.game_state import GameStateManager, InMemoryGameStateRepository
from shared.contracts.dialogue import DialogueDraft, DialogueMessage
```
