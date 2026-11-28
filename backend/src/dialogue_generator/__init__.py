"""LEGACY dialogue pipeline: PreparedDialogueTurn in, validated DialogueDraft out.

No longer on the API execution path. The backend now calls ``src.llm.InterrogationService``
(see ``docs/backend_integration_guide.md``); its quality checks live in
``src.llm.reply_checks``. Kept temporarily for reference; nothing in ``api/`` imports it.
"""

from .pipeline import DialoguePipeline, DialogueResult

__all__ = ["DialoguePipeline", "DialogueResult"]
