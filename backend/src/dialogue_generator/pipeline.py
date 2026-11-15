"""Ties the dialogue steps together: context -> prompt -> LLM -> parse -> validate."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shared.contracts.dialogue import DialogueDraft
from shared.contracts.errors import ContractValidationError
from src.case_engine import CaseEngine
from src.llm import FactExtractor
from src.progression.authorization import PreparedDialogueTurn

from .context_builder import build_context
from .llm_adapter import LLMAdapter, LLMError
from .prompt_builder import build_prompt
from .response_validator import fallback_draft, validate

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # first try + one stricter retry


@dataclass(frozen=True)
class DialogueResult:
    draft: DialogueDraft
    is_fallback: bool
    attempts: int
    problems: tuple[str, ...] = ()


class DialoguePipeline:
    def __init__(self, engine: CaseEngine, adapter: LLMAdapter | None = None):
        self.engine = engine
        self.adapter = adapter or LLMAdapter()
        self.extractor = FactExtractor()

    def generate(self, turn: PreparedDialogueTurn) -> DialogueResult:
        """Always returns a usable draft; model problems end in the fallback line."""
        request = turn.request
        ctx = build_context(turn, self.engine)
        problems: list[str] = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = build_prompt(ctx, strict=attempt > 1)
            try:
                result = self.adapter.generate(prompt)
                if result.truncated:
                    problems.append("model output was cut off")
                    continue
                draft = self.extractor.extract(result.text, request, result.metrics).draft
            except (LLMError, ContractValidationError, ValueError) as exc:
                problems.append(str(exc))
                continue

            found = validate(draft, ctx)
            if not found:
                return DialogueResult(draft, False, attempt, tuple(problems))
            problems += found

        log.warning("dialogue fallback for %s: %s", request.request_id, problems)
        return DialogueResult(fallback_draft(request), True, MAX_ATTEMPTS, tuple(problems))
