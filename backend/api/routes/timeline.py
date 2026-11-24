from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import CaseSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, CaseIdPath
from ..schemas.responses import ApiEnvelope, ListData, TimelineEventPublic

router = APIRouter(prefix="/cases", tags=["Cases"], responses=ERROR_RESPONSES)


@router.get(
    "/{case_id}/timeline",
    response_model=ApiEnvelope[ListData[TimelineEventPublic]],
    summary="Public timeline (backstory only)",
    description="Events whose facts are all public background. Events describing the crime "
    "itself are withheld. Items follow the case file's declared order, not a verified chronology.",
)
def list_timeline(case_id: CaseIdPath, request_id: RequestId, cases: CaseSvc):
    items = cases.list_timeline(case_id)
    return success(request_id, ListData[TimelineEventPublic](items=items, count=len(items)))
