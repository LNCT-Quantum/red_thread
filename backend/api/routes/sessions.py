from __future__ import annotations

from fastapi import APIRouter, Query

from ..config import API_PREFIX
from ..dependencies import GameSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, SessionIdPath
from ..schemas.requests import CreateSessionRequest
from ..schemas.responses import (
    ApiEnvelope,
    HistoryData,
    ProgressData,
    SessionCreated,
    SessionDeleted,
    SessionState,
)

router = APIRouter(prefix="/sessions", tags=["Sessions"], responses=ERROR_RESPONSES)


@router.post(
    "",
    status_code=201,
    response_model=ApiEnvelope[SessionCreated],
    summary="Create a game session",
    description="Sessions are held in memory and are lost when the backend restarts.",
)
def create_session(body: CreateSessionRequest, request_id: RequestId, games: GameSvc):
    created = games.create_session(body.case_id)
    return success(
        request_id,
        created,
        status_code=201,
        headers={"Location": f"{API_PREFIX}/sessions/{created.session_id}"},
    )


@router.get("/{session_id}", response_model=ApiEnvelope[SessionState], summary="Current game state")
def get_session(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.get_session(session_id))


@router.delete(
    "/{session_id}",
    response_model=ApiEnvelope[SessionDeleted],
    summary="Delete a session",
    description="Permanently removes the session and its dialogue history.",
)
def delete_session(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.delete_session(session_id))


@router.get(
    "/{session_id}/history",
    response_model=ApiEnvelope[HistoryData],
    summary="Conversation history",
)
def get_history(
    session_id: SessionIdPath,
    request_id: RequestId,
    games: GameSvc,
    npc_id: str | None = Query(default=None, min_length=1, max_length=128, description="Only this NPC's conversation."),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return success(request_id, games.history(session_id, npc_id, limit, offset))


@router.get(
    "/{session_id}/progress",
    response_model=ApiEnvelope[ProgressData],
    summary="Progress summary and discovered information",
)
def get_progress(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.progress(session_id))
