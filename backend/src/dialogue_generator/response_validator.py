"""Step 5: quality checks on the parsed draft, plus the safe reply used when they keep failing.

Fact and clue ID checks are already done by FactExtractor, so they are not repeated here.
"""

from __future__ import annotations

import re

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics

from .context_builder import DialogueContext

MAX_CHARS = 600
LEAK_WINDOW = 5  # this many words copied from a hidden fact counts as a leak

AI_SPEAK = re.compile(
    r"as an ai|language model|i am an ai|i'm an ai|i cannot assist|i'm sorry, but|\bfact_\d{3}\b|\bclue_\d{3}\b",
    re.IGNORECASE,
)


def validate(draft: DialogueDraft, ctx: DialogueContext) -> list[str]:
    """Return a list of problems. Empty list means the draft is fine."""
    problems = []

    text = draft.content.strip()
    if len(text) < 2 or text == "...":
        problems.append("empty reply")
    if len(text) > MAX_CHARS:
        problems.append("reply too long")
    if AI_SPEAK.search(text):
        problems.append("out of character or exposes internal ids")
    if _leaks_hidden_fact(text, ctx.hidden_statements):
        problems.append("repeats a fact this NPC must not know")

    return problems


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _leaks_hidden_fact(reply: str, hidden: tuple[str, ...]) -> bool:
    reply_words = _words(reply)
    reply_grams = {tuple(reply_words[i:i + LEAK_WINDOW]) for i in range(len(reply_words) - LEAK_WINDOW + 1)}
    if not reply_grams:
        return False
    for statement in hidden:
        words = _words(statement)
        for i in range(len(words) - LEAK_WINDOW + 1):
            if tuple(words[i:i + LEAK_WINDOW]) in reply_grams:
                return True
    return False


FALLBACK_LINES = [
    "I'd rather not go into that right now, detective.",
    "I don't think I can help you with that.",
    "Ask me something else. I have nothing more to say on that.",
]


def fallback_draft(request: DialogueRequest) -> DialogueDraft:
    return DialogueDraft(
        request_id=request.request_id,
        suspect_id=request.suspect_id,
        content=FALLBACK_LINES[len(request.player_message) % len(FALLBACK_LINES)],
        cited_fact_ids=(),
        cited_clue_ids=(),
        metrics=GenerationMetrics("fallback", 0.0, 0.0, 0, 0),
    )
