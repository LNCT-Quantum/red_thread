"""Unified Interrogation Service: The single facade for Red Thread LLM Integration.

Bridges backend contracts (DialogueRequest, Suspect) directly with:
1. Dynamic Prompt Synthesis (prompt_synthesizer.py)
2. Local Streaming Inference (engine_runner.py)
3. Latency & TTFT SLA Profiling (profiler.py)
4. Fact Extraction & Citation Sanitization (extractor.py)
5. In-character quality checks (reply_checks.py)

The service never decides *what* an NPC may know. The caller (the backend's Progression
Gate) supplies an authorized ``DialogueRequest`` plus the resolved evidence reactions; the
service only renders that context, runs the model and sanitizes the reply against it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Iterator

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics
from shared.contracts.errors import ContractValidationError
from shared.contracts.suspect import Suspect

from .engine_runner import EngineError, LocalLLMEngine
from .extractor import ExtractionResult, FactExtractor
from .profiler import LatencyProfiler
from .prompt_synthesizer import build_prompt
from .reply_checks import check_reply

log = logging.getLogger(__name__)

SAFE_FALLBACK_TEXT = (
    "I'd rather not speak on that right now, detective. There are things I cannot discuss."
)


@dataclass(frozen=True, slots=True)
class InterrogationResponse:
    """Complete response returned to the backend caller."""

    draft: DialogueDraft
    extraction_result: ExtractionResult
    prompt_used: str
    is_fallback: bool
    fallback_reason: str | None = None
    attempts: int = 1
    problems: tuple[str, ...] = ()


def _looks_like_broken_json(text: str) -> bool:
    return "{" in text or "}" in text or '"content"' in text or "cited_fact_ids" in text


class _EngineFailure(Exception):
    """An error event reported by the engine stream (unavailable, timeout, crash...)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InterrogationService:
    """Unified Facade for the LLM Integration subsystem.

    This is the single class the Backend and Game Engine call to interrogate suspects.
    """

    def __init__(
        self,
        engine: LocalLLMEngine | None = None,
        extractor: FactExtractor | None = None,
        profiler: LatencyProfiler | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.engine = engine or LocalLLMEngine()
        self.extractor = extractor or FactExtractor(strip_unauthorized=True)
        self.profiler = profiler or LatencyProfiler(target_ttft_ms=800.0)
        self.max_attempts = max(1, int(max_attempts))

    # ------------------------------------------------------------------ public API
    def generate_reply(
        self,
        request: DialogueRequest,
        *,
        suspect: Suspect | dict[str, Any] | None = None,
        knowledge: Any | None = None,
        clues: Any | None = None,
        revision: int | None = None,
        reactions: Iterable[Any] = (),
        concealed_fact_ids: Iterable[str] = (),
        hidden_statements: Iterable[str] = (),
    ) -> InterrogationResponse:
        """Executes one complete interrogation turn from DialogueRequest to DialogueDraft.

        Args:
            request: The Progression-Gate-authorized ``DialogueRequest``.
            suspect: The ``Suspect`` contract (persona, background, speech style).
            knowledge: The facts the NPC may use (``Fact`` contracts or fact records).
            clues: The presented clues (``Clue`` contracts or clue records).
            revision: ``GameState.revision`` used for reveal-level gating.
            reactions: ``PreparedDialogueTurn.reactions`` for the presented clues.
            concealed_fact_ids: Authorized facts the suspect hides (its secrets).
            hidden_statements: Statements of facts the NPC must NOT reveal; a reply that
                repeats their wording is rejected.

        Never raises for model problems: unusable output ends in a safe fallback draft
        that cites nothing (``is_fallback=True``).
        """
        reactions = tuple(reactions or ())
        concealed = tuple(concealed_fact_ids or ())
        hidden = tuple(hidden_statements or ())
        req_data = self._prepare_request_data(request, revision)
        problems: list[str] = []
        prompt = ""

        for attempt in range(1, self.max_attempts + 1):
            try:
                prompt = build_prompt(
                    req_data,
                    suspect=suspect,
                    knowledge=knowledge,
                    clues=clues,
                    reactions=reactions,
                    concealed_fact_ids=concealed,
                    strict=attempt > 1,
                )
            except (ValueError, TypeError, FileNotFoundError) as exc:
                # The authorized context could not be rendered; never guess at it.
                log.error("Prompt synthesis failed for %s: %s", request.request_id, exc)
                return self.fallback_reply(request, f"prompt synthesis failed: {exc}", prompt)

            try:
                raw_text, metrics, truncated = self._run_engine(prompt)
            except _EngineFailure as exc:
                # Unavailable server / timeout / runner crash: retrying would only add latency.
                log.warning("Engine failure (%s) for %s: %s", exc.code, request.request_id, exc)
                problems.append(f"{exc.code}: {exc}")
                return self.fallback_reply(request, str(exc), prompt, attempt, problems)

            if truncated:
                problems.append("model output was cut off")
                continue

            try:
                extraction_res = self.extractor.extract(raw_text, request, metrics)
            except (ContractValidationError, ValueError, TypeError) as exc:
                problems.append(f"extraction failed: {exc}")
                continue

            found = check_reply(extraction_res.draft.content, hidden)
            if extraction_res.parse_strategy == "fallback_regex" and _looks_like_broken_json(
                extraction_res.draft.content
            ):
                # Unparseable JSON fragments must never be shown to the player as speech.
                found.append("malformed JSON output")
            if found:
                problems.extend(found)
                continue

            return InterrogationResponse(
                draft=extraction_res.draft,
                extraction_result=extraction_res,
                prompt_used=prompt,
                is_fallback=False,
                fallback_reason=None,
                attempts=attempt,
                problems=tuple(problems),
            )

        log.warning("Dialogue fallback for %s: %s", request.request_id, problems)
        return self.fallback_reply(
            request, "; ".join(problems) or "no usable reply", prompt, self.max_attempts, problems
        )

    def stream_reply(
        self,
        request: DialogueRequest,
        *,
        suspect: Suspect | dict[str, Any] | None = None,
        knowledge: Any | None = None,
        clues: Any | None = None,
        revision: int | None = None,
        reactions: Iterable[Any] = (),
        concealed_fact_ids: Iterable[str] = (),
        hidden_statements: Iterable[str] = (),
    ) -> Iterator[dict[str, Any]]:
        """Yields streaming token events for live UI typewriter rendering, ending with completed draft."""
        req_data = self._prepare_request_data(request, revision)
        try:
            prompt = build_prompt(
                req_data,
                suspect=suspect,
                knowledge=knowledge,
                clues=clues,
                reactions=tuple(reactions or ()),
                concealed_fact_ids=tuple(concealed_fact_ids or ()),
            )
        except (ValueError, TypeError, FileNotFoundError) as exc:
            yield {"type": "error", "error": {"code": "PROMPT_SYNTHESIS_FAILED", "message": str(exc)}}
            yield {"type": "done", "response": self.fallback_reply(request, str(exc))}
            return

        tokens: list[str] = []
        ttft_ms: float | None = None
        eval_count: int | None = None
        prompt_eval_count = 0
        truncated = False

        for event in self.engine.stream_generate(prompt, response_format="json"):
            event_type = event.get("type")
            if event_type == "token":
                tok = event.get("token", "")
                tokens.append(tok)
                if ttft_ms is None:
                    ttft_ms = event.get("ttft_ms")
                yield {"type": "token", "token": tok, "ttft_ms": ttft_ms}

            elif event_type == "complete":
                m = event.get("metrics", {}) or {}
                eval_count = m.get("eval_count")
                prompt_eval_count = m.get("prompt_eval_count") or 0
                truncated = bool(event.get("truncated"))

            elif event_type == "error":
                err = event.get("error", {})
                yield {"type": "error", "error": err}
                fallback = self.fallback_reply(request, str(err), prompt)
                yield {"type": "done", "response": fallback}
                return

        raw_text, metrics = self.profiler.measure_stream(
            iter(tokens),
            model_id=self._model_id(),
            prompt_tokens=prompt_eval_count,
        )
        metrics = self._merge_engine_metrics(metrics, ttft_ms, eval_count)

        problems: tuple[str, ...] = ("model output was cut off",) if truncated else ()
        resp: InterrogationResponse | None = None
        if not problems:
            try:
                extraction_res = self.extractor.extract(raw_text, request, metrics)
                found = tuple(check_reply(extraction_res.draft.content, hidden_statements))
                if extraction_res.parse_strategy == "fallback_regex" and _looks_like_broken_json(
                    extraction_res.draft.content
                ):
                    found += ("malformed JSON output",)
                if found:
                    problems = found
                else:
                    resp = InterrogationResponse(
                        draft=extraction_res.draft,
                        extraction_result=extraction_res,
                        prompt_used=prompt,
                        is_fallback=False,
                    )
            except (ContractValidationError, ValueError, TypeError) as exc:
                problems = (f"extraction failed: {exc}",)
        if resp is None:
            resp = self.fallback_reply(request, "; ".join(problems), prompt, 1, problems)
        yield {"type": "done", "response": resp}

    def fallback_reply(
        self,
        request: DialogueRequest,
        reason: str,
        prompt: str = "",
        attempts: int = 1,
        problems: Iterable[str] = (),
    ) -> InterrogationResponse:
        """An in-character deflection that cites no fact or clue (safe to show any time).

        A fallback delivers no evidence reaction, so callers must not record one-time
        reactions as consumed for it.
        """
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
            content=SAFE_FALLBACK_TEXT,
            cited_fact_ids=(),
            cited_clue_ids=(),
            metrics=safe_metrics,
        )
        extraction_res = ExtractionResult(
            draft=fallback_draft,
            parse_strategy="safe_fallback",
            raw_content=SAFE_FALLBACK_TEXT,
            stripped_fact_ids=(),
            stripped_clue_ids=(),
        )
        return InterrogationResponse(
            draft=fallback_draft,
            extraction_result=extraction_res,
            prompt_used=prompt,
            is_fallback=True,
            fallback_reason=reason,
            attempts=attempts,
            problems=tuple(problems),
        )

    # Backwards-compatible name used by earlier callers.
    def _create_fallback_response(
        self, request: DialogueRequest, prompt: str, reason: str
    ) -> InterrogationResponse:
        return self.fallback_reply(request, reason, prompt)

    # ------------------------------------------------------------------ internals
    def _run_engine(self, prompt: str) -> tuple[str, GenerationMetrics, bool]:
        """Streams one generation through the profiler; raises ``_EngineFailure`` on error events."""
        state: dict[str, Any] = {
            "ttft_ms": None, "eval_count": None, "prompt_eval_count": 0,
            "truncated": False, "error": None, "completed": False,
        }

        def tokens() -> Iterator[str]:
            try:
                for event in self.engine.stream_generate(prompt, response_format="json"):
                    event_type = event.get("type")
                    if event_type == "token":
                        if state["ttft_ms"] is None:
                            state["ttft_ms"] = event.get("ttft_ms")
                        yield event.get("token", "")
                    elif event_type == "complete":
                        m = event.get("metrics", {}) or {}
                        state["eval_count"] = m.get("eval_count")
                        state["prompt_eval_count"] = m.get("prompt_eval_count") or 0
                        state["truncated"] = bool(event.get("truncated"))
                        state["completed"] = True
                    elif event_type == "error":
                        err = event.get("error", {}) or {}
                        state["error"] = (
                            str(err.get("code", "ENGINE_ERROR")),
                            str(err.get("message", "Inference error")),
                        )
                        return
            except EngineError as exc:  # engines are expected to yield errors, but be safe
                state["error"] = (getattr(exc, "code", "ENGINE_ERROR"), str(exc))
            except Exception as exc:  # noqa: BLE001 - a broken engine must not crash the turn
                state["error"] = ("ENGINE_ERROR", f"{type(exc).__name__}: {exc}")

        raw_text, metrics = self.profiler.measure_stream(
            tokens(), model_id=self._model_id(), prompt_tokens=0
        )
        if state["error"] is not None:
            raise _EngineFailure(*state["error"])
        if not state["completed"] and not raw_text.strip():
            raise _EngineFailure("EMPTY_COMPLETION", "The engine returned no output.")

        metrics = GenerationMetrics(
            model_id=metrics.model_id,
            time_to_first_token_ms=metrics.time_to_first_token_ms,
            generation_time_ms=metrics.generation_time_ms,
            prompt_tokens=int(state["prompt_eval_count"] or 0),
            completion_tokens=metrics.completion_tokens,
        )
        metrics = self._merge_engine_metrics(metrics, state["ttft_ms"], state["eval_count"])
        return raw_text, metrics, bool(state["truncated"])

    @staticmethod
    def _merge_engine_metrics(
        metrics: GenerationMetrics, ttft_ms: float | None, eval_count: int | None
    ) -> GenerationMetrics:
        """Prefer the engine's socket-level TTFT and token count when it reports them."""
        if ttft_ms is None and eval_count is None:
            return metrics
        ttft = float(ttft_ms) if ttft_ms is not None else metrics.time_to_first_token_ms
        return GenerationMetrics(
            model_id=metrics.model_id,
            time_to_first_token_ms=ttft,
            generation_time_ms=max(metrics.generation_time_ms, ttft),
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=eval_count if eval_count is not None else metrics.completion_tokens,
        )

    def _model_id(self) -> str:
        config = getattr(self.engine, "config", None)
        return str(getattr(config, "model_name", None) or "unknown-model")

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
