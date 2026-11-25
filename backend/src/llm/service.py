"""Unified Interrogation Service: The single facade for Red Thread LLM Integration.

Bridges backend contracts (DialogueRequest, Suspect) directly with:
1. Dynamic Prompt Synthesis (prompt_synthesizer.py)
2. Local Streaming Inference (engine_runner.py)
3. Latency & TTFT SLA Profiling (profiler.py)
4. Fact Extraction & Citation Sanitization (extractor.py)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterator

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics
from shared.contracts.suspect import Suspect

from .engine_runner import EngineError, LocalLLMEngine
from .extractor import ExtractionResult, FactExtractor
from .profiler import LatencyProfiler
from .prompt_synthesizer import build_prompt

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InterrogationResponse:
    """Complete response returned to the backend caller."""

    draft: DialogueDraft
    extraction_result: ExtractionResult
    prompt_used: str
    is_fallback: bool
    fallback_reason: str | None = None


class InterrogationService:
    """Unified Facade for the LLM Integration subsystem.

    This is the single class the Backend and Game Engine call to interrogate suspects.
    """

    def __init__(
        self,
        engine: LocalLLMEngine | None = None,
        extractor: FactExtractor | None = None,
        profiler: LatencyProfiler | None = None,
    ) -> None:
        self.engine = engine or LocalLLMEngine()
        self.extractor = extractor or FactExtractor(strip_unauthorized=True)
        self.profiler = profiler or LatencyProfiler(target_ttft_ms=800.0)

    def generate_reply(
        self,
        request: DialogueRequest,
        *,
        suspect: Suspect | dict[str, Any] | None = None,
        knowledge: Any | None = None,
        clues: Any | None = None,
        revision: int | None = None,
    ) -> InterrogationResponse:
        """Executes one complete interrogation turn from DialogueRequest to DialogueDraft."""
        # 1. Prepare request mapping for synthesizer (supporting revision)
        req_data = self._prepare_request_data(request, revision)

        # 2. Synthesize prompt directly from backend contracts
        prompt = build_prompt(
            req_data,
            suspect=suspect,
            knowledge=knowledge,
            clues=clues,
        )

        try:
            # 3. Stream from local engine runner while profiling socket latency
            raw_tokens: list[str] = []
            ttft_ms: float | None = None
            eval_count: int | None = None
            prompt_eval_count = 0

            for event in self.engine.stream_generate(prompt, response_format="json"):
                event_type = event.get("type")
                if event_type == "error":
                    err_msg = event.get("error", {}).get("message", "Inference error")
                    log.warning("Engine reported error: %s", err_msg)
                    return self._create_fallback_response(request, prompt, err_msg)

                if event_type == "token":
                    raw_tokens.append(event.get("token", ""))
                    if ttft_ms is None:
                        ttft_ms = event.get("ttft_ms")

                elif event_type == "complete":
                    m = event.get("metrics", {})
                    eval_count = m.get("eval_count")
                    prompt_eval_count = m.get("prompt_eval_count") or 0

            # Measure stream through profiler
            raw_text, metrics = self.profiler.measure_stream(
                iter(raw_tokens),
                model_id=self.engine.config.model_name,
                prompt_tokens=prompt_eval_count,
            )

            # Override with engine socket ttft if available
            if ttft_ms is not None:
                gen_time = max(metrics.generation_time_ms, ttft_ms)
                metrics = GenerationMetrics(
                    model_id=metrics.model_id,
                    time_to_first_token_ms=ttft_ms,
                    generation_time_ms=gen_time,
                    prompt_tokens=metrics.prompt_tokens,
                    completion_tokens=eval_count or metrics.completion_tokens,
                )

            # 4. Extract, sanitize, and validate citations
            extraction_res = self.extractor.extract(raw_text, request, metrics)

            return InterrogationResponse(
                draft=extraction_res.draft,
                extraction_result=extraction_res,
                prompt_used=prompt,
                is_fallback=False,
                fallback_reason=None,
            )

        except (EngineError, Exception) as exc:
            log.warning("Interrogation failed with exception: %s. Using fallback.", exc)
            return self._create_fallback_response(request, prompt, str(exc))

    def stream_reply(
        self,
        request: DialogueRequest,
        *,
        suspect: Suspect | dict[str, Any] | None = None,
        knowledge: Any | None = None,
        clues: Any | None = None,
        revision: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yields streaming token events for live UI typewriter rendering, ending with completed draft."""
        req_data = self._prepare_request_data(request, revision)
        prompt = build_prompt(
            req_data,
            suspect=suspect,
            knowledge=knowledge,
            clues=clues,
        )

        tokens: list[str] = []
        ttft_ms: float | None = None
        eval_count: int | None = None
        prompt_eval_count = 0

        for event in self.engine.stream_generate(prompt, response_format="json"):
            event_type = event.get("type")
            if event_type == "token":
                tok = event.get("token", "")
                tokens.append(tok)
                if ttft_ms is None:
                    ttft_ms = event.get("ttft_ms")
                yield {"type": "token", "token": tok, "ttft_ms": ttft_ms}

            elif event_type == "complete":
                m = event.get("metrics", {})
                eval_count = m.get("eval_count")
                prompt_eval_count = m.get("prompt_eval_count") or 0

            elif event_type == "error":
                err = event.get("error", {})
                yield {"type": "error", "error": err}
                fallback = self._create_fallback_response(request, prompt, str(err))
                yield {"type": "done", "response": fallback}
                return

        raw_text, metrics = self.profiler.measure_stream(
            iter(tokens),
            model_id=self.engine.config.model_name,
            prompt_tokens=prompt_eval_count,
        )
        if ttft_ms is not None:
            gen_time = max(metrics.generation_time_ms, ttft_ms)
            metrics = GenerationMetrics(
                model_id=metrics.model_id,
                time_to_first_token_ms=ttft_ms,
                generation_time_ms=gen_time,
                prompt_tokens=metrics.prompt_tokens,
                completion_tokens=eval_count or metrics.completion_tokens,
            )

        extraction_res = self.extractor.extract(raw_text, request, metrics)
        resp = InterrogationResponse(
            draft=extraction_res.draft,
            extraction_result=extraction_res,
            prompt_used=prompt,
            is_fallback=False,
        )
        yield {"type": "done", "response": resp}

    def _prepare_request_data(self, request: DialogueRequest, revision: int | None) -> dict[str, Any]:
        req_data: dict[str, Any] = {
            "request_id": request.request_id,
            "case_id": request.case_id,
            "suspect_id": request.suspect_id,
            "player_message": request.player_message,
            "authorized_fact_ids": list(request.authorized_fact_ids),
            "presented_clue_ids": list(request.presented_clue_ids),
            "dialogue_history": list(request.dialogue_history),
            "revision": revision if revision is not None else 0,
        }
        return req_data

    def _create_fallback_response(
        self, request: DialogueRequest, prompt: str, reason: str
    ) -> InterrogationResponse:
        """Constructs an in-character deflection draft when inference fails or is offline."""
        safe_fallback_text = (
            "I'd rather not speak on that right now, detective. There are things I cannot discuss."
        )
        safe_metrics = GenerationMetrics(
            model_id="fallback",
            time_to_first_token_ms=0.0,
            generation_time_ms=0.0,
            prompt_tokens=0,
            completion_tokens=0,
        )
        fallback_draft = DialogueDraft(
            request_id=request.request_id,
            suspect_id=request.suspect_id,
            content=safe_fallback_text,
            cited_fact_ids=(),
            cited_clue_ids=(),
            metrics=safe_metrics,
        )
        extraction_res = ExtractionResult(
            draft=fallback_draft,
            parse_strategy="safe_fallback",
            raw_content=safe_fallback_text,
            stripped_fact_ids=(),
            stripped_clue_ids=(),
        )
        return InterrogationResponse(
            draft=fallback_draft,
            extraction_result=extraction_res,
            prompt_used=prompt,
            is_fallback=True,
            fallback_reason=reason,
        )
