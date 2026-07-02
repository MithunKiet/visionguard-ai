from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.zone.application.services import ZoneService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user

router = APIRouter(prefix="/zones", tags=["Zones"])


@router.get("", response_model=ApiResponse[list], summary="List zones (with factory/department names)")
async def list_zones(
    factory_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse(data=await ZoneService(db).list_zones(UUID(user.enterprise_id), factory_id))
