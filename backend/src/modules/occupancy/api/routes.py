import math
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.occupancy.application.services import OccupancyService
from src.modules.occupancy.infrastructure.repositories import OccupancyRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user

router = APIRouter(prefix="/occupancy", tags=["Occupancy"])


def _get_service(db: AsyncSession = Depends(get_db)) -> OccupancyService:
    return OccupancyService(OccupancyRepository(db))


@router.get("/current", response_model=ApiResponse[list], summary="Latest occupancy per zone")
async def current_occupancy(
    user: AuthUser = Depends(get_current_user),
    svc: OccupancyService = Depends(_get_service),
):
    return ApiResponse(data=await svc.current(UUID(user.enterprise_id)))


@router.get("/history", response_model=ApiResponse[list], summary="Occupancy log history")
async def occupancy_history(
    zone_id: UUID | None = None,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: AuthUser = Depends(get_current_user),
    svc: OccupancyService = Depends(_get_service),
):
    items, total = await svc.history(
        UUID(user.enterprise_id), zone_id, from_dt, to_dt, page, page_size
    )
    return ApiResponse(
        data=items,
        meta=MetaResponse(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 1,
        ),
    )
