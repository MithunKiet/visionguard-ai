from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.analytics.application.services import AnalyticsService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/violations", response_model=ApiResponse[dict], summary="Violation trends")
async def violation_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    zone_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.violations(UUID(user.enterprise_id), from_dt, to_dt, zone_id))


@router.get("/occupancy", response_model=ApiResponse[dict], summary="Occupancy analytics")
async def occupancy_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    zone_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.occupancy(UUID(user.enterprise_id), from_dt, to_dt, zone_id))


@router.get("/compliance", response_model=ApiResponse[dict], summary="Alert resolution + SLA compliance")
async def compliance_analytics(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.compliance(UUID(user.enterprise_id), from_dt, to_dt))


@router.get("/safety-score", response_model=ApiResponse[dict], summary="Overall safety score (0-100)")
async def safety_score(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    user: AuthUser = Depends(get_current_user),
    svc: AnalyticsService = Depends(_get_service),
):
    return ApiResponse(data=await svc.safety_score(UUID(user.enterprise_id), from_dt, to_dt))
