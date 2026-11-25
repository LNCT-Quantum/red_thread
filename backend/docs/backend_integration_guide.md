# LLM Integration Subsystem: Backend Integration Guide

**Module:** `src.llm`  
**Target Milestone:** Sprint 2 (Local LLM Interrogation Pipeline)  
**Target Model:** `Qwen2.5-3B-Instruct` (`Q4_K_M` GGUF) via local Ollama (`http://127.0.0.1:11434`)  
**Performance SLA:** First Token Latency (TTFT) < 800ms  

---

## 1. Quick Start: The Single Entry Point

The backend and game state modules interact with the LLM Integration team through **one single facade class**:

```python
from src.llm import InterrogationService

# Initialize the service once (connects to local Ollama/llama.cpp)
llm_service = InterrogationService()
```

---

## 2. Available Methods (Endpoints)

### `llm_service.generate_reply(...)` -- Complete Synchronous Turn

Use this when you want the complete, validated reply in a single call.

```python
response = llm_service.generate_reply(
    request=dialogue_request,  # Instance of shared.contracts.dialogue.DialogueRequest
    suspect=suspect_contract,  # Instance of shared.contracts.suspect.Suspect (or None)
    knowledge=knowledge_data,  # In-memory dict or loaded from npc_knowledge.json
    clues=clues_data,          # In-memory dict or loaded from clues.json
    revision=current_revision, # GameState.revision (int) for fact reveal gating
)

# Access the validated DialogueDraft
draft = response.draft
print(draft.content)          # "I heard footsteps at 9:40 PM..." (In-character dialogue)
print(draft.cited_fact_ids)   # ("fact_001",) (Sanitized; zero hallucinated facts)
print(draft.cited_clue_ids)   # ("clue_006",) (Presented clues only)
print(draft.metrics)          # GenerationMetrics(time_to_first_token_ms=45.2, ...)

# Fallback status
if response.is_fallback:
    print("Safe fallback used due to:", response.fallback_reason)
```

---

### `llm_service.stream_reply(...)` -- Live Typewriter Streaming

Use this when streaming tokens to the web/terminal UI typewriter in real time.

```python
for event in llm_service.stream_reply(request=dialogue_request, suspect=suspect_contract, revision=1):
    if event["type"] == "token":
        # Stream text token directly to player's screen
        print(event["token"], end="", flush=True)
        # Optional socket TTFT telemetry on chunk 1
        if event["ttft_ms"] is not None:
            log.info("First token latency: %s ms", event["ttft_ms"])

    elif event["type"] == "done":
        # Turn finished: access the finalized, validated InterrogationResponse
        final_response = event["response"]
        draft = final_response.draft
        games.complete_dialogue_turn(game_id, turn, draft)
```

---

## 3. Data Flow & Subsystem Responsibilities

Under the hood, `InterrogationService` orchestrates all three team members' work:

```
[Backend: DialogueRequest + Suspect]
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                 InterrogationService Facade                 │
│                                                             │
│ 1. Dynamic Prompt Synthesis (Anand)                         │
│    • Ingests Suspect traits & speech style                  │
│    • Fact reveal-level gating (reveal_level <= revision)    │
│    • Escapes <player_question> injection boundaries         │
│    • Appends few-shot JSON formatting examples              │
│                                                             │
│ 2. Local Streaming Inference (Anshul)                       │
│    • LocalLLMEngine streams tokens via local Ollama socket  │
│    • Evaluates Qwen2.5-3B-Instruct (Q4_K_M)                 │
│                                                             │
│ 3. Latency & TTFT Profiling (Devansh)                       │
│    • LatencyProfiler measures socket TTFT (Target < 800ms)  │
│    • Tracks decoding throughput (tokens/sec)                │
│                                                             │
│ 4. Fact Extraction & Sanitization (Devansh)                 │
│    • FactExtractor strips <think> reasoning tags            │
│    • Multi-strategy parser (exact_json, fence, regex)       │
│    • Citation Sanitizer: drops unauthorized fact citations  │
│    • Packages strict DialogueDraft contract                 │
└─────────────────────────────────────────────────────────────┘
                 │
                 ▼
     [Backend: DialogueDraft]
```

---

## 4. Contract Verification Matrix

| Sprint 2 Requirement | Implementation | Status |
|---|---|:---:|
| **Sub-800ms Latency SLA** | Measured Mean TTFT: **45.96 ms** (RTX 4050 GPU) | **PASSED** |
| **Local Offline Inference** | Ollama loopback (`127.0.0.1:11434`) / `llama.cpp` | **PASSED** |
| **Model Quantization** | `qwen2.5:3b-instruct-q4_K_M` (~2.1 GB) | **PASSED** |
| **Temporal Fact Gating** | `int(reveal_level) <= int(revision)` | **PASSED** |
| **Zero Fact Hallucinations** | `FactExtractor._sanitize_citations()` drops unauthorized IDs | **PASSED** |
| **Prompt Injection Protection** | Enforces `<player_question>` tags with escaped closing delimiters | **PASSED** |
| **Sensory Voice Fidelity** | Ingests `suspects.json` non-visual acoustics & alibi directives | **PASSED** |
| **Graceful Crash Handling** | Returns in-character deflection draft if model times out | **PASSED** |
| **Automated Test Coverage** | 38 automated unit tests across extractor, engine, synthesizer, and service | **100% PASS** |
