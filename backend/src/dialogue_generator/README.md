# Dialogue Generator

This folder makes the NPC (suspect) reply when the player asks a question.

**Simple idea:** the game decides what the suspect is allowed to know. This folder only turns that into a natural reply, using a local AI model.

> The Case Engine owns the truth. The LLM owns the voice. This folder protects the mystery.

---

## What goes in and what comes out

- **In:** one `PreparedDialogueTurn`. The game state module makes it with `prepare_dialogue_turn(...)`.
- **Out:** one `DialogueResult`. It has:
  - `draft` – the reply (a `DialogueDraft`). The text is in `draft.content`.
  - `is_fallback` – `True` if the AI failed and we used a safe reply.
  - `attempts` – how many tries it took (1 or 2).
  - `problems` – why a try failed (useful for debugging).

---

## The files

| File | What it does |
|---|---|
| `context_builder.py` | Collects what the suspect may use: facts, clues shown, personality, last 6 messages. |
| `prompt_builder.py` | Writes the text we send to the AI. |
| `llm_adapter.py` | Sends the text to the AI model and gets the answer and timing. |
| `response_validator.py` | Checks the answer. Also has the safe reply for when the AI fails. |
| `pipeline.py` | Runs all the steps in order. This is the file you call. |
| `tests/test_dialogue_pipeline.py` | Tests. They use a fake AI, so Ollama is not needed. |

We also use code from other people. **We do not change it.**

| Used file | Used for |
|---|---|
| `src/case_engine/engine.py` | Get fact text, clue text and suspect details. |
| `src/llm/engine_runner.py` | Talk to Ollama. |
| `src/llm/extractor.py` | Read the AI answer and remove facts the suspect may not use. |
| `shared/contracts/dialogue.py` | The shared data types. |

---

## How one question works

1. Player asks a question. The game state module prepares the turn.
2. `context_builder.py` collects the allowed facts, clues and personality.
3. `prompt_builder.py` writes the prompt.
4. `llm_adapter.py` sends it to the AI model.
5. `extractor.py` reads the answer and removes any fact ID that is not allowed.
6. `response_validator.py` checks the answer.
7. If the answer is good, we return it.
8. If it is bad, we try **one more time** with a stricter prompt.
9. If it is bad again (or the AI is down), we return a safe reply like "I'd rather not go into that right now, detective." and set `is_fallback=True`.

The game never crashes because of a bad AI answer.

---

## What the validator rejects

- Empty reply, or longer than 600 characters.
- Replies like "As an AI language model...".
- Replies that show internal IDs such as `fact_001`.
- Replies that copy 5 or more words in a row from a fact the suspect must not know.
- Answers that were cut off before they finished.

---

## How to use it

Do this once when the game starts:

```python
from src.case_engine import CaseEngine
from src.progression import ProgressionGate
from src.game_state import GameStateManager, InMemoryGameStateRepository
from src.dialogue_generator import DialoguePipeline
from src.llm.engine_runner import initialize_engine

initialize_engine(warmup=True)   # loads the model so the first question is not slow
case = CaseEngine.load("case_001")
games = GameStateManager(case, InMemoryGameStateRepository(), ProgressionGate.from_engine(case))
pipeline = DialoguePipeline(case)
```

Do this for every player question:

```python
turn = games.prepare_dialogue_turn(
    game_id,
    request_id="any_unique_id",
    suspect_id="suspect_001",
    player_message="Where were you last night?",
    dialogue_session_id="session_1",
)
result = pipeline.generate(turn)

games.complete_dialogue_turn(game_id, turn, result.draft)
# then save the player message and the reply with games.append_dialogue_message(...)
# then show result.draft.content to the player
```

---

## What you need to run it

- Python 3.10 or newer.
- `pip install requests pytest`
- Ollama running, with the model pulled (default: `qwen2.5:3b-instruct-q4_K_M`).
- Use `127.0.0.1` and not `localhost` for Ollama. On Windows `localhost` can be slow.

The model and its settings come from environment variables read by `src/llm/engine_runner.py`. For example: `OLLAMA_MODEL`, `LLM_NUM_PREDICT`, `LLM_TEMPERATURE`.

If Ollama is not running, the pipeline still works. Every reply will be the safe fallback reply.

---

## Run the tests

From the `backend/` folder:

```
python -m pytest src/dialogue_generator/tests -q
```

---

## What this folder does NOT do

- It does **not** decide which facts a suspect can know. The backend does that.
- It does **not** change the game state or unlock clues.
- It does **not** save messages. The caller does that.
- It does **not** have an API route. The controller or API owner calls `pipeline.generate(turn)`.

---

## Known limits

- The "copied hidden fact" check only finds copied words. If the AI says the same thing in new words, it will not be caught.
- It was tested with a fake AI. Run a few real questions with Ollama and read the replies. You may need to change the rules in `prompt_builder.py`.
- In the worst case there are two AI calls for one question.
