from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ppe.application.services import PPEService
from src.modules.ppe.infrastructure.repositories import ViolationRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user
import math

router = APIRouter(prefix="/violations", tags=["PPE Violations"])


def _get_service(db: AsyncSession = Depends(get_db)) -> PPEService:
    return PPEService(ViolationRepository(db))


@router.get("", response_model=ApiResponse[list], summary="List violations")
async def list_violations(
    zone_id: UUID | None = None,
    camera_id: UUID | None = None,
    violation_type: str | None = None,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
    svc: PPEService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    items, total = await svc.list_violations(
        _UUID(user.enterprise_id),
        zone_id, camera_id, violation_type,
        from_dt, to_dt, page, page_size,
    )
    return ApiResponse(
        data=items,
        meta=MetaResponse(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size),
        ),
    )


@router.get("/{violation_id}", response_model=ApiResponse[dict], summary="Get violation detail")
async def get_violation(
    violation_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: PPEService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    item = await svc.get_violation(violation_id, _UUID(user.enterprise_id))
    return ApiResponse(data=item)
