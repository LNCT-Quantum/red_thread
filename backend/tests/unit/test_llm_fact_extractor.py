from __future__ import annotations

import pytest

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics
from shared.contracts.errors import ContractValidationError
from src.llm import FactExtractor


@pytest.fixture
def sample_metrics() -> GenerationMetrics:
    return GenerationMetrics(
        model_id="qwen2.5-3b-instruct-q4",
        time_to_first_token_ms=450.0,
        generation_time_ms=1200.0,
        prompt_tokens=180,
        completion_tokens=45,
    )


@pytest.fixture
def sample_request() -> DialogueRequest:
    return DialogueRequest(
        request_id="req_test_001",
        case_id="case_001",
        suspect_id="suspect_001",
        player_message="Where were you on the night of the murder?",
        authorized_fact_ids=("fact_001", "fact_021", "fact_023"),
        presented_clue_ids=("clue_006",),
    )


def test_clean_json_extraction(sample_request: DialogueRequest, sample_metrics: GenerationMetrics) -> None:
    raw_response = """{
        "content": "I was at home practising my cello. I lost my eyesight years ago.",
        "cited_fact_ids": ["fact_001", "fact_021"],
        "cited_clue_ids": ["clue_006"]
    }"""
    extractor = FactExtractor()
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert result.parse_strategy == "exact_json"
    assert result.draft.content == "I was at home practising my cello. I lost my eyesight years ago."
    assert result.draft.cited_fact_ids == ("fact_001", "fact_021")
    assert result.draft.cited_clue_ids == ("clue_006",)
    assert not result.stripped_fact_ids


def test_markdown_fence_extraction(sample_request: DialogueRequest, sample_metrics: GenerationMetrics) -> None:
    raw_response = """```json
    {
        "content": "I recognize footsteps by rhythm, not sight.",
        "cited_fact_ids": ["fact_023"],
        "cited_clue_ids": ["clue_006"]
    }
    ```"""
    extractor = FactExtractor()
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert result.parse_strategy == "markdown_fence"
    assert "recognize footsteps" in result.draft.content
    assert result.draft.cited_fact_ids == ("fact_023",)


def test_preamble_and_enclosed_json(sample_request: DialogueRequest, sample_metrics: GenerationMetrics) -> None:
    raw_response = """Certainly, Detective Aarav. Here is my statement:
    {
        "content": "I have not seen Dr. Malhotra in two weeks.",
        "cited_fact_ids": ["fact_001"],
        "cited_clue_ids": []
    }
    Hope this helps your investigation."""
    extractor = FactExtractor()
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert result.parse_strategy == "enclosed_object"
    assert "two weeks" in result.draft.content
    assert result.draft.cited_fact_ids == ("fact_001",)


def test_stripping_think_tags(sample_request: DialogueRequest, sample_metrics: GenerationMetrics) -> None:
    raw_response = """<think>
    The user is asking about my blindness. Fact_021 is authorized.
    I must stay composed.
    </think>
    {
        "content": "I lost my eyesight at nineteen.",
        "cited_fact_ids": ["fact_021"],
        "cited_clue_ids": []
    }"""
    extractor = FactExtractor()
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert "<think>" not in result.draft.content
    assert result.draft.cited_fact_ids == ("fact_021",)


def test_strips_unauthorized_facts_by_default(
    sample_request: DialogueRequest, sample_metrics: GenerationMetrics
) -> None:
    raw_response = """{
        "content": "I know Kabir transferred money and I know Rishabh.",
        "cited_fact_ids": ["fact_001", "fact_028", "fact_999"],
        "cited_clue_ids": ["clue_006", "clue_099"]
    }"""
    extractor = FactExtractor(strip_unauthorized=True)
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert result.draft.cited_fact_ids == ("fact_001",)
    assert set(result.stripped_fact_ids) == {"fact_028", "fact_999"}
    assert result.draft.cited_clue_ids == ("clue_006",)
    assert result.stripped_clue_ids == ("clue_099",)


def test_raises_error_when_strip_unauthorized_disabled(
    sample_request: DialogueRequest, sample_metrics: GenerationMetrics
) -> None:
    raw_response = """{
        "content": "Unauthorized leak statement.",
        "cited_fact_ids": ["fact_028"],
        "cited_clue_ids": []
    }"""
    extractor = FactExtractor(strip_unauthorized=False)
    with pytest.raises(ContractValidationError) as exc_info:
        extractor.extract(raw_response, sample_request, sample_metrics)

    assert exc_info.value.code == "DRAFT_UNAUTHORIZED_FACT"


def test_fallback_regex_on_plain_text(
    sample_request: DialogueRequest, sample_metrics: GenerationMetrics
) -> None:
    raw_response = "I lost my vision at nineteen as noted in fact_021, and heard footsteps clue_006."
    extractor = FactExtractor()
    result = extractor.extract(raw_response, sample_request, sample_metrics)

    assert result.parse_strategy == "fallback_regex"
    assert result.draft.content == raw_response
    assert result.draft.cited_fact_ids == ("fact_021",)
    assert result.draft.cited_clue_ids == ("clue_006",)
