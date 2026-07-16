from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.config.api.schemas import UpdateZoneConfigRequest
from src.modules.config.application.services import ConfigService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/config", tags=["Config"])

_ADMIN_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ConfigService:
    return ConfigService(db)


@router.get("/zone/{zone_id}", response_model=ApiResponse[dict], summary="Get zone detection config")
async def get_zone_config(
    zone_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: ConfigService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_zone_config(zone_id, user.enterprise_id))


@router.put("/zone/{zone_id}", response_model=ApiResponse[dict], summary="Update zone config (hot-applied to AI workers)")
async def update_zone_config(
    zone_id: str,
    body: UpdateZoneConfigRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ConfigService = Depends(_get_service),
):
    return ApiResponse(data=await svc.update_zone_config(
        zone_id,
        user.enterprise_id,
        body.model_dump(exclude={"change_reason"}),
        user.user_id,
        body.change_reason,
    ))


@router.get("/zone/{zone_id}/history", response_model=ApiResponse[list], summary="Zone config change history")
async def zone_config_history(
    zone_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ConfigService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_history(zone_id, user.enterprise_id, limit))


@router.post("/zone/{zone_id}/restore/{history_id}", response_model=ApiResponse[dict], summary="Restore config from a history entry")
async def restore_zone_config(
    zone_id: str,
    history_id: str,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ConfigService = Depends(_get_service),
):
    return ApiResponse(data=await svc.restore(
        zone_id, user.enterprise_id, history_id, user.user_id
    ))
