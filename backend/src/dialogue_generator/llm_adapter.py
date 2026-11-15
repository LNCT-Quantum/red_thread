"""Step 3: thin wrapper over Devansh's LocalLLMEngine (src/llm/engine_runner.py)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from shared.contracts.dialogue import GenerationMetrics
from src.llm.engine_runner import LocalLLMEngine


class LLMError(RuntimeError):
    """The model could not give us a usable answer."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    metrics: GenerationMetrics
    truncated: bool


class LLMAdapter:
    def __init__(self, engine=None):
        self.engine = engine or LocalLLMEngine()

    def generate(self, prompt: str) -> LLMResult:
        started = time.perf_counter()
        done = None
        for event in self.engine.stream_generate(prompt, response_format="json"):
            if event["type"] == "error":
                raise LLMError(event["error"]["message"])
            if event["type"] == "complete":
                done = event
        if done is None:
            raise LLMError("stream ended without a result")

        total_ms = (time.perf_counter() - started) * 1000
        m = done["metrics"]
        ttft = min(m.get("client_ttft_ms") or 0.0, total_ms)
        metrics = GenerationMetrics(
            model_id=self.engine.config.model_name,
            time_to_first_token_ms=ttft,
            generation_time_ms=total_ms,
            prompt_tokens=m.get("prompt_eval_count") or 0,
            completion_tokens=m.get("eval_count"),
        )
        return LLMResult(done["text"], metrics, done["truncated"])
