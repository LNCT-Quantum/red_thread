from __future__ import annotations

from fastapi import APIRouter, Body

from ..dependencies import CaseSvc, GameSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, CaseIdPath, ClueIdPath, SessionIdPath
from ..schemas.requests import DiscoverClueRequest
from ..schemas.responses import (
    ApiEnvelope,
    ClueDiscoveryData,
    ClueList,
    ClueSummary,
    EvidenceData,
    ListData,
)

router = APIRouter(tags=["Clues"], responses=ERROR_RESPONSES)


@router.get(
    "/cases/{case_id}/clues",
    response_model=ApiEnvelope[ListData[ClueSummary]],
    summary="Clues collectable at the start of the case",
    description="Title and location only. Descriptions are revealed when a clue is discovered "
    "inside a session. Later clues are not listed.",
)
def list_case_clues(case_id: CaseIdPath, request_id: RequestId, cases: CaseSvc):
    items = cases.list_clues(case_id)
    return success(request_id, ListData[ClueSummary](items=items, count=len(items)))


@router.get(
    "/sessions/{session_id}/clues",
    response_model=ApiEnvelope[ClueList],
    summary="Clues this player has discovered",
)
def list_discovered_clues(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.list_discovered_clues(session_id))


@router.post(
    "/sessions/{session_id}/clues/{clue_id}/discover",
    response_model=ApiEnvelope[ClueDiscoveryData],
    summary="Discover (collect) a clue",
    description="Authorized by the progression gate: a locked clue returns 403 CLUE_LOCKED. "
    "Discovering an already discovered clue is a harmless no-op (`already_discovered: true`).",
)
def discover_clue(
    session_id: SessionIdPath,
    clue_id: ClueIdPath,
    request_id: RequestId,
    games: GameSvc,
    body: DiscoverClueRequest | None = Body(default=None),
):
    expected = body.expected_revision if body else None
    return success(request_id, games.discover_clue(session_id, clue_id, expected))


@router.get(
    "/sessions/{session_id}/evidence",
    response_model=ApiEnvelope[EvidenceData],
    summary="Evidence board: collected and currently collectable evidence",
)
def get_evidence(session_id: SessionIdPath, request_id: RequestId, games: GameSvc):
    return success(request_id, games.evidence(session_id))
