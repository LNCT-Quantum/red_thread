"""In-character quality checks on an extracted DialogueDraft.

Fact and clue ID authorization is enforced by ``FactExtractor``; these checks cover what
ID sanitization cannot see: empty/oversized replies, the model breaking character or
exposing internal IDs, and the reply repeating the wording of a fact this NPC is not
authorized to use (a leak of an unrevealed part of the mystery).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["MAX_REPLY_CHARS", "LEAK_WINDOW", "check_reply"]

MAX_REPLY_CHARS = 600
LEAK_WINDOW = 5  # this many consecutive words copied from a hidden fact counts as a leak

_AI_SPEAK = re.compile(
    r"as an ai|language model|i am an ai|i'm an ai|i cannot assist|i'm sorry, but"
    r"|\bfact_\d{3}\b|\bclue_\d{3}\b",
    re.IGNORECASE,
)


def check_reply(content: str, hidden_statements: Iterable[str] = ()) -> list[str]:
    """Return the problems found in ``content``; an empty list means the reply is usable."""
    problems: list[str] = []
    text = (content or "").strip()
    if len(text) < 2 or text == "...":
        problems.append("empty reply")
    if len(text) > MAX_REPLY_CHARS:
        problems.append("reply too long")
    if _AI_SPEAK.search(text):
        problems.append("out of character or exposes internal ids")
    if _leaks_hidden_fact(text, tuple(hidden_statements)):
        problems.append("repeats a fact this NPC must not know")
    return problems


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _leaks_hidden_fact(reply: str, hidden: tuple[str, ...]) -> bool:
    reply_words = _words(reply)
    reply_grams = {
        tuple(reply_words[i : i + LEAK_WINDOW]) for i in range(len(reply_words) - LEAK_WINDOW + 1)
    }
    if not reply_grams:
        return False
    for statement in hidden:
        words = _words(statement)
        for i in range(len(words) - LEAK_WINDOW + 1):
            if tuple(words[i : i + LEAK_WINDOW]) in reply_grams:
                return True
    return False
