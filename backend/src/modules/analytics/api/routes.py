from src.shared.security.resource_policy import enforce_resource_scope
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.analytics.application.services import AnalyticsService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user
from src.shared.security.scope import get_scope

router = APIRouter(dependencies=[Depends(enforce_resource_scope)], prefix="/analytics", tags=["Analytics"])


def _get_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/detection-health", response_model=ApiResponse[dict], summary="Current detection availability with scoped camera details")
async def current_detection_health(
    page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
    problems_only: bool = False, zone_id: str | None = None,
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from src.modules.analytics.application.detection_health import detection_health
    result = await detection_health(db, user.enterprise_id, get_scope(user), page, page_size, problems_only, zone_id)
    total = result.pop("total")
    return ApiResponse(data=result, meta=MetaResponse(page=page, page_size=page_size, total=total,
        total_pages=max(1, (total + page_size - 1) // page_size)))


@router.get("/violations", response_model=ApiResponse[dict], summary="Violation trends")
async def violation_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    zone_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.violations(user.enterprise_id, from_dt, to_dt, zone_id, get_scope(user)))


@router.get("/occupancy", response_model=ApiResponse[dict], summary="Occupancy analytics")
async def occupancy_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    zone_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.occupancy(user.enterprise_id, from_dt, to_dt, zone_id, get_scope(user)))


@router.get("/compliance", response_model=ApiResponse[dict], summary="Alert resolution + SLA compliance")
async def compliance_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.compliance(user.enterprise_id, from_dt, to_dt, get_scope(user)))


@router.get("/safety-score", response_model=ApiResponse[dict], summary="Overall safety score (0-100)")
async def safety_score(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.safety_score(user.enterprise_id, from_dt, to_dt, get_scope(user)))
