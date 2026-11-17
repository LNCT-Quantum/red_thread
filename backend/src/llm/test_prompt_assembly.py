"""Focused tests for prompt assembly and epistemic fact gating.

Run from this directory:
    python -m unittest -v
"""

import unittest

from prompt_synthesizer import build_prompt


KNOWLEDGE = {
    "facts": [
        {
            "fact_id": "fact_001",
            "reveal_level": 0,
            "text": "Anaya is a musician.",
        },
        {
            "fact_id": "fact_010",
            "reveal_level": 2,
            "text": "A permitted case detail revealed at stage two.",
        },
        {
            "fact_id": "fact_099",
            "reveal_level": 4,
            "text": "A future fact that must remain hidden.",
        },
    ]
}

REQUEST = {
    "suspect_id": "suspect_001",
    "player_message": {"role": "player", "content": "What did you hear?"},
    "authorized_fact_ids": ["fact_001", "fact_010", "fact_099"],
    "dialogue_history": [
        {"role": "player", "content": "Hello"},
        {"role": "suspect", "content": "I am listening."},
    ],
    "revision": 2,
}


class PromptAssemblyTests(unittest.TestCase):
    def test_includes_only_authorized_and_revealed_facts(self):
        prompt = build_prompt(REQUEST, knowledge=KNOWLEDGE)
        self.assertIn("fact_001: Anaya is a musician.", prompt)
        self.assertIn("fact_010: A permitted case detail revealed at stage two.", prompt)
        self.assertNotIn("A future fact that must remain hidden.", prompt)

    def test_anaya_sensory_rules_are_present(self):
        prompt = build_prompt(REQUEST, knowledge=KNOWLEDGE)
        self.assertIn("blind musician", prompt.lower())
        self.assertIn("Never claim to see", prompt)
        self.assertIn("sound", prompt.lower())
        self.assertIn("touch", prompt.lower())

    def test_history_is_limited_to_last_four_turns(self):
        request = dict(REQUEST)
        request["dialogue_history"] = [
            {"role": "player", "content": f"turn-{i}"} for i in range(6)
        ]
        prompt = build_prompt(request, knowledge=KNOWLEDGE)
        self.assertNotIn("turn-0", prompt)
        self.assertNotIn("turn-1", prompt)
        self.assertIn("turn-2", prompt)
        self.assertIn("turn-5", prompt)

    def test_unknown_suspect_is_rejected(self):
        request = dict(REQUEST, suspect_id="suspect_999")
        with self.assertRaises(ValueError):
            build_prompt(request, knowledge=KNOWLEDGE)

    def test_unknown_authorized_fact_is_rejected(self):
        request = dict(REQUEST, authorized_fact_ids=["fact_missing"])
        with self.assertRaises(ValueError):
            build_prompt(request, knowledge=KNOWLEDGE)

    def test_revision_is_required(self):
        request = dict(REQUEST)
        request.pop("revision")
        with self.assertRaises(ValueError):
            build_prompt(request, knowledge=KNOWLEDGE)

    def test_player_question_is_delimited(self):
        prompt = build_prompt(REQUEST, knowledge=KNOWLEDGE)
        self.assertIn("<player_question>", prompt)
        self.assertIn("</player_question>", prompt)

    def test_required_output_schema_is_present(self):
        prompt = build_prompt(REQUEST, knowledge=KNOWLEDGE)
        self.assertIn('"cited_fact_ids"', prompt)
        self.assertIn('"cited_clue_ids"', prompt)


if __name__ == "__main__":
    unittest.main()
