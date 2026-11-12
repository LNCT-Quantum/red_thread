from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Pattern

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics
from shared.contracts.errors import ContractValidationError

FACT_ID_PATTERN: Pattern[str] = re.compile(r"\bfact_\d{3}\b", re.IGNORECASE)
CLUE_ID_PATTERN: Pattern[str] = re.compile(r"\bclue_\d{3}\b", re.IGNORECASE)
THINK_TAG_PATTERN: Pattern[str] = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
MARKDOWN_JSON_PATTERN: Pattern[str] = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    draft: DialogueDraft
    parse_strategy: str
    raw_content: str
    stripped_fact_ids: tuple[str, ...]
    stripped_clue_ids: tuple[str, ...]


class FactExtractor:
    """Extracts, sanitizes, and packages LLM interrogation output into DialogueDraft."""

    def __init__(self, strip_unauthorized: bool = True) -> None:
        self.strip_unauthorized = strip_unauthorized

    def extract(
        self,
        raw_text: str,
        request: DialogueRequest,
        metrics: GenerationMetrics,
    ) -> ExtractionResult:
        cleaned_text = self._strip_reasoning_tags(raw_text)
        parsed, strategy = self._parse_json_payload(cleaned_text)

        if parsed:
            content = str(parsed.get("content", "")).strip()
            raw_facts = self._extract_id_sequence(parsed.get("cited_fact_ids", ()))
            raw_clues = self._extract_id_sequence(parsed.get("cited_clue_ids", ()))
        else:
            strategy = "fallback_regex"
            content = cleaned_text.strip()
            raw_facts = tuple(sorted(set(FACT_ID_PATTERN.findall(cleaned_text))))
            raw_clues = tuple(sorted(set(CLUE_ID_PATTERN.findall(cleaned_text))))

        if not content:
            content = "..."

        valid_facts: list[str] = []
        stripped_facts: list[str] = []
        for fact_id in raw_facts:
            normalized_fact = fact_id.lower()
            if request.has_authorized_fact(normalized_fact):
                if normalized_fact not in valid_facts:
                    valid_facts.append(normalized_fact)
            else:
                if self.strip_unauthorized:
                    stripped_facts.append(normalized_fact)
                else:
                    valid_facts.append(normalized_fact)

        valid_clues: list[str] = []
        stripped_clues: list[str] = []
        for clue_id in raw_clues:
            normalized_clue = clue_id.lower()
            if request.has_presented_clue(normalized_clue):
                if normalized_clue not in valid_clues:
                    valid_clues.append(normalized_clue)
            else:
                if self.strip_unauthorized:
                    stripped_clues.append(normalized_clue)
                else:
                    valid_clues.append(normalized_clue)

        draft = DialogueDraft(
            request_id=request.request_id,
            suspect_id=request.suspect_id,
            content=content,
            cited_fact_ids=tuple(valid_facts),
            cited_clue_ids=tuple(valid_clues),
            metrics=metrics,
        )
        draft.validate_against_request(request)

        return ExtractionResult(
            draft=draft,
            parse_strategy=strategy,
            raw_content=content,
            stripped_fact_ids=tuple(stripped_facts),
            stripped_clue_ids=tuple(stripped_clues),
        )

    def _strip_reasoning_tags(self, text: str) -> str:
        return THINK_TAG_PATTERN.sub("", text).strip()

    def _parse_json_payload(self, text: str) -> tuple[dict[str, Any] | None, str]:
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                return parsed, "exact_json"
        except (ValueError, TypeError):
            pass

        match = MARKDOWN_JSON_PATTERN.search(text)
        if match:
            try:
                parsed = json.loads(match.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed, "markdown_fence"
            except (ValueError, TypeError):
                pass

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            snippet = text[first_brace : last_brace + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed, "enclosed_object"
            except (ValueError, TypeError):
                pass

        return None, "fallback_regex"

    @staticmethod
    def _extract_id_sequence(value: Any) -> tuple[str, ...]:
        if isinstance(value, (list, tuple)):
            items: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    items.append(item.strip())
            return tuple(items)
        if isinstance(value, str):
            return tuple(re.findall(r"(?:fact|clue)_\d{3}", value, re.IGNORECASE))
        return ()
