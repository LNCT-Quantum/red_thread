"""Compact few-shot examples for structured, grounded suspect replies.

Examples demonstrate output shape and sensory style only. The cited IDs are
illustrative and must also be present in the request's authorized ID lists.
"""

FEW_SHOT_EXAMPLES = [
    {
        "player_question": "What did you notice around the hallway at that time?",
        "authorized_context": (
            "Illustrative authorized clue: clue_006 — a testimony about footsteps "
            "at 9:40 PM. No other details are supplied."
        ),
        "assistant_output": {
            "content": (
                "I remember the rhythm of footsteps. I cannot tell you more "
                "than what that sound allowed me to know."
            ),
            "cited_fact_ids": [],
            "cited_clue_ids": ["clue_006"],
        },
    },
    {
        "player_question": "What colour was the person's jacket?",
        "authorized_context": (
            "No authorized fact or clue establishes the person's clothing."
        ),
        "assistant_output": {
            "content": (
                "I couldn't have identified a colour. I did not see the person; "
                "I can only speak about what I heard or physically sensed."
            ),
            "cited_fact_ids": [],
            "cited_clue_ids": [],
        },
    },
]


def render_few_shot_examples() -> str:
    """Render examples as readable prompt text."""
    import json

    blocks = []
    for index, example in enumerate(FEW_SHOT_EXAMPLES, start=1):
        blocks.append(
            f"EXAMPLE {index}\n"
            f"Player question: {example['player_question']}\n"
            f"Authorized context: {example['authorized_context']}\n"
            "Correct JSON response:\n"
            + json.dumps(example["assistant_output"], ensure_ascii=False)
        )
    return "\n\n".join(blocks)
