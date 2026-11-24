from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import RequestId, SystemSvc
from ..envelope import failure, success
from ..schemas.responses import ApiEnvelope, HealthData, ReadyData

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=ApiEnvelope[HealthData], summary="Is the backend running?")
def health(request_id: RequestId, system: SystemSvc):
    return success(request_id, system.health())


@router.get(
    "/ready",
    response_model=ApiEnvelope[ReadyData],
    summary="Are the game components initialized and ready?",
    responses={503: {"model": ApiEnvelope[None], "description": "Not ready"}},
)
def ready(request_id: RequestId, system: SystemSvc):
    report = system.readiness()
    if report.ready:
        return success(request_id, report)
    details = [f"{name}: {c.status}" + (f" ({c.detail})" if c.detail else "")
               for name, c in report.components.items() if c.status != "ok"]
    return failure(request_id, 503, "NOT_READY", "The backend is not ready to serve games", details)
