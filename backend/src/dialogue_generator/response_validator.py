"""Step 5: quality checks on the parsed draft, plus the safe reply used when they keep failing.

Fact and clue ID checks are already done by FactExtractor, so they are not repeated here.
"""

from __future__ import annotations

from shared.contracts.dialogue import DialogueDraft, DialogueRequest, GenerationMetrics

from .context_builder import DialogueContext

from src.llm.reply_checks import check_reply


def validate(draft: DialogueDraft, ctx: DialogueContext) -> list[str]:
    """Return a list of problems. Empty list means the draft is fine (see src.llm.reply_checks)."""
    return check_reply(draft.content, ctx.hidden_statements)


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
