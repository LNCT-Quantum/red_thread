from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import DialogueSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, SessionIdPath
from ..schemas.requests import DialogueTurnRequest
from ..schemas.responses import ApiEnvelope, DialogueData

router = APIRouter(tags=["Dialogue"], responses=ERROR_RESPONSES)


@router.post(
    "/sessions/{session_id}/dialogue",
    response_model=ApiEnvelope[DialogueData],
    summary="Ask an NPC a question",
    description="Runs the full backend pipeline (progression authorization, LLM, response "
    "validation) and stores both lines in the session history. This call can take several "
    "seconds; set a generous client timeout.",
)
def post_dialogue(
    session_id: SessionIdPath, body: DialogueTurnRequest, request_id: RequestId, dialogue: DialogueSvc
):
    return success(
        request_id,
        dialogue.take_turn(
            session_id=session_id,
            npc_id=body.npc_id,
            message=body.message,
            presented_clue_ids=body.presented_clue_ids,
            expected_revision=body.expected_revision,
            request_id=request_id,
        ),
    )
