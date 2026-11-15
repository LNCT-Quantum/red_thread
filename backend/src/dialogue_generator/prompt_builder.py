"""Step 2: build the text prompt sent to the local model."""

from __future__ import annotations

from .context_builder import DialogueContext

MAX_PLAYER_CHARS = 500


def build_prompt(ctx: DialogueContext, strict: bool = False) -> str:
    s = ctx.suspect
    lines = [
        f"You are {s.name}, a {s.age}-year-old {s.occupation}, being questioned by a detective "
        "about a murder. Stay in character at all times.",
        f"Background: {s.background}",
        f"Relationship to the victim: {s.relationship_to_victim}",
        f"Personality: {', '.join(s.personality_traits)}",
        f"How you speak: {s.speech_style}",
        "",
        "Facts you know (you may mention them, cite them by ID):",
    ]
    lines += [f"[{f.fact_id}] {f.statement}" for f in ctx.facts]

    if ctx.clues:
        lines += ["", "The detective is showing you this evidence:"]
        lines += [f"[{c.clue_id}] {c.title}: {c.description}" for c in ctx.clues]
        for r in ctx.reactions:
            lines.append(_reaction_line(r))

    lines += [
        "",
        "Rules:",
        "- Only talk about the facts listed above. Do not invent names, places, times or events.",
        "- If asked about something not listed, say you don't know or deflect, in character.",
        "- Never confess to anything that is not listed above.",
        "- Reply in English, 1 to 3 sentences, spoken dialogue only.",
    ]
    if strict:
        lines.append("- Your last answer was rejected. Stay in character and use ONLY the listed facts.")

    if ctx.history:
        lines += ["", "Conversation so far:"]
        lines += [f"{who}: {text}" for who, text in ctx.history]

    question = ctx.player_message[:MAX_PLAYER_CHARS]
    lines += [
        "",
        f"Detective: {question}",
        "",
        'Answer with JSON only: {"content": "<what you say>", '
        '"cited_fact_ids": ["fact_xxx"], "cited_clue_ids": ["clue_xxx"]}',
    ]
    return "\n".join(lines)


def _reaction_line(r) -> str:
    text = f"Your reaction to {r.clue_id}: you feel {r.emotional_response}."
    if r.stated_position:
        text += f" Your position: {r.stated_position}"
    if r.reveal_fact_ids and not r.is_repeat:
        text += f" You may now admit: {', '.join(r.reveal_fact_ids)}."
    if r.conceal_fact_ids:
        text += f" Avoid discussing: {', '.join(r.conceal_fact_ids)}."
    if r.limits:
        text += f" Limit: {r.limits}"
    return text
