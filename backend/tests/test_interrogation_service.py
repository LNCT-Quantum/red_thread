"""Tests for the unified InterrogationService facade."""

from __future__ import annotations

import unittest
from typing import Any, Iterator

from shared.contracts.dialogue import DialogueDraft, DialogueRequest
from shared.contracts.suspect import Suspect
from src.llm.service import InterrogationService


class MockEngine:
    def __init__(self, token_events: list[dict[str, Any]] | None = None) -> None:
        self.token_events = token_events or [
            {"type": "token", "token": '{"content": "I heard ', "ttft_ms": 42.5},
            {"type": "token", "token": 'footsteps at 9:40 PM.", ', "ttft_ms": None},
            {"type": "token", "token": '"cited_fact_ids": ["fact_001"], ', "ttft_ms": None},
            {"type": "token", "token": '"cited_clue_ids": ["clue_006"]}', "ttft_ms": None},
            {
                "type": "complete",
                "text": '{"content": "I heard footsteps at 9:40 PM.", "cited_fact_ids": ["fact_001"], "cited_clue_ids": ["clue_006"]}',
                "metrics": {
                    "eval_count": 25,
                    "prompt_eval_count": 50,
                    "client_ttft_ms": 42.5,
                },
            },
        ]
        self.config = type("Config", (), {"model_name": "qwen2.5:3b"})()

    def stream_generate(self, prompt: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
        for event in self.token_events:
            yield event


class MockFailingEngine:
    def __init__(self) -> None:
        self.config = type("Config", (), {"model_name": "qwen2.5:3b"})()

    def stream_generate(self, prompt: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
        yield {"type": "error", "error": {"message": "Ollama connection timeout"}}


class InterrogationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = DialogueRequest(
            request_id="req_test_001",
            case_id="case_001",
            suspect_id="suspect_001",
            player_message="Did you hear anything?",
            authorized_fact_ids=("fact_001",),
            presented_clue_ids=("clue_006",),
        )
        self.suspect = Suspect(
            suspect_id="suspect_001",
            name="Anaya Kapoor",
            occupation="Musician",
            background="A blind musician who lost her eyesight at 19.",
            public_description="Composed young woman listening closely.",
            relationship_to_victim="Acquaintance of Rishabh.",
            speech_style="Measured and quiet with deliberate pauses.",
            age=29,
            personality_traits=("guarded", "perceptive"),
        )
        self.knowledge = {
            "facts": [
                {"fact_id": "fact_001", "reveal_level": 0, "statement": "Anaya is a musician."}
            ]
        }

    def test_generate_reply_end_to_end_success(self) -> None:
        service = InterrogationService(engine=MockEngine())
        response = service.generate_reply(
            self.request,
            suspect=self.suspect,
            knowledge=self.knowledge,
            revision=1,
        )

        self.assertFalse(response.is_fallback)
        self.assertIsInstance(response.draft, DialogueDraft)
        self.assertEqual(response.draft.content, "I heard footsteps at 9:40 PM.")
        self.assertEqual(response.draft.cited_fact_ids, ("fact_001",))
        self.assertEqual(response.draft.cited_clue_ids, ("clue_006",))
        self.assertIn("<player_question>", response.prompt_used)
        self.assertIn("Anaya Kapoor", response.prompt_used)
        self.assertGreater(response.draft.metrics.time_to_first_token_ms, 0)

    def test_generate_reply_fallback_on_engine_failure(self) -> None:
        service = InterrogationService(engine=MockFailingEngine())
        response = service.generate_reply(
            self.request,
            suspect=self.suspect,
            knowledge=self.knowledge,
            revision=1,
        )

        self.assertTrue(response.is_fallback)
        self.assertIn("rather not speak", response.draft.content.lower())
        self.assertEqual(response.draft.cited_fact_ids, ())
        self.assertEqual(response.draft.metrics.model_id, "fallback")

    def test_stream_reply_yields_tokens_and_done(self) -> None:
        service = InterrogationService(engine=MockEngine())
        events = list(
            service.stream_reply(
                self.request,
                suspect=self.suspect,
                knowledge=self.knowledge,
                revision=1,
            )
        )

        token_events = [e for e in events if e["type"] == "token"]
        done_events = [e for e in events if e["type"] == "done"]

        self.assertEqual(len(token_events), 4)
        self.assertEqual(len(done_events), 1)
        resp = done_events[0]["response"]
        self.assertFalse(resp.is_fallback)
        self.assertEqual(resp.draft.content, "I heard footsteps at 9:40 PM.")


if __name__ == "__main__":
    unittest.main()
