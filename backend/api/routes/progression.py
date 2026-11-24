from __future__ import annotations

from fastapi import APIRouter, Body

from ..dependencies import GameSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, SessionIdPath, SuspectIdPath
from ..schemas.requests import CompleteInterviewRequest
from ..schemas.responses import ApiEnvelope, InterviewData, ProgressionData, UnlocksData

router = APIRouter(tags=["Progression"], responses=ERROR_RESPONSES)


@router.get(
    "/sessions/{session_id}/progression",
    response_model=ApiEnvelope[ProgressionData],
    summary="Investigation stage progression",
)
def get_progression(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.progression(session_id))


@router.get(
    "/sessions/{session_id}/unlocks",
    response_model=ApiEnvelope[UnlocksData],
    summary="Information currently unlocked for this player",
)
def get_unlocks(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.unlocks(session_id))


@router.post(
    "/sessions/{session_id}/interviews/{suspect_id}/complete",
    response_model=ApiEnvelope[InterviewData],
    summary="Complete an interview with a suspect",
    description="Needed for progression (some stages and testimony clues require completed "
    "interviews). Refused with 409 INTERVIEW_NOT_READY until the suspect has actually "
    "answered the player. Stages are evaluated by the progression gate, never by the client.",
)
def complete_interview(
    session_id: SessionIdPath,
    suspect_id: SuspectIdPath,
    request_id: RequestId,
    games: GameSvc,
    body: CompleteInterviewRequest | None = Body(default=None),
):
    expected = body.expected_revision if body else None
    return success(request_id, games.complete_interview(session_id, suspect_id, expected))
