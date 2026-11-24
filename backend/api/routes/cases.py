from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import CaseSvc, RequestId
from ..envelope import success
from ._common import ERROR_RESPONSES, CaseIdPath
from ..schemas.responses import ApiEnvelope, CaseDetail, CaseSummary, FactPublic, ListData

router = APIRouter(prefix="/cases", tags=["Cases"], responses=ERROR_RESPONSES)


@router.get("", response_model=ApiEnvelope[ListData[CaseSummary]], summary="List playable cases")
def list_cases(request_id: RequestId, cases: CaseSvc):
    items = cases.list_cases()
    return success(request_id, ListData[CaseSummary](items=items, count=len(items)))


@router.get("/{case_id}", response_model=ApiEnvelope[CaseDetail], summary="Case metadata")
def get_case(case_id: CaseIdPath, request_id: RequestId, cases: CaseSvc):
    return success(request_id, cases.get_case(case_id))


@router.get(
    "/{case_id}/facts",
    response_model=ApiEnvelope[ListData[FactPublic]],
    summary="Public background facts",
    description="Only baseline facts known at the start of the investigation. Evidence-linked, "
    "stage-gated and secret facts are never returned.",
)
def list_facts(case_id: CaseIdPath, request_id: RequestId, cases: CaseSvc):
    items = cases.list_facts(case_id)
    return success(request_id, ListData[FactPublic](items=items, count=len(items)))
