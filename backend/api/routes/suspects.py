from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import CaseSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, CaseIdPath
from ..schemas.responses import ApiEnvelope, ListData, SuspectPublic

router = APIRouter(prefix="/cases", tags=["Cases"], responses=ERROR_RESPONSES)


@router.get(
    "/{case_id}/suspects",
    response_model=ApiEnvelope[ListData[SuspectPublic]],
    summary="Suspects (public profile)",
)
def list_suspects(case_id: CaseIdPath, request_id: RequestId, cases: CaseSvc):
    items = cases.list_suspects(case_id)
    return success(request_id, ListData[SuspectPublic](items=items, count=len(items)))
