from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.zone.api.schemas import CreateZoneRequest, UpdateZoneRequest
from src.modules.zone.application.services import ZoneService
from src.modules.zone.infrastructure.repositories import ZoneRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/zones", tags=["Zones"])

_ADMIN_ROLES = ("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ZoneService:
    return ZoneService(ZoneRepository(db), db)


@router.get("", response_model=ApiResponse[list], summary="List zones (with factory/department names)")
async def list_zones(
    factory_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: ZoneService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_zones(UUID(user.enterprise_id), factory_id))


@router.post("", response_model=ApiResponse[dict], summary="Create zone (+ default PPE config)")
async def create_zone(
    body: CreateZoneRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ZoneService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    zone = await svc.create_zone(
        UUID(user.enterprise_id), body.factory_id, body.department_id, body.name, body.code,
        body.max_occupancy, body.zone_type, body.is_restricted, body.supervisor_id, body.ppe_required,
    )
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="ZONE_CREATED",
        entity_type="zone",
        entity_id=zone.id,
        new_value=svc.to_dict(zone),
    )
    return ApiResponse(data=svc.to_dict(zone))


@router.get("/{zone_id}", response_model=ApiResponse[dict], summary="Get zone")
async def get_zone(
    zone_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: ZoneService = Depends(_get_service),
):
    zone = await svc.get_zone(zone_id, UUID(user.enterprise_id))
    return ApiResponse(data=svc.to_dict(zone))


@router.put("/{zone_id}", response_model=ApiResponse[dict], summary="Update zone")
async def update_zone(
    zone_id: UUID,
    body: UpdateZoneRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ZoneService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    zone = await svc.update_zone(
        zone_id, UUID(user.enterprise_id), **body.model_dump(exclude_none=True)
    )
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="ZONE_UPDATED",
        entity_type="zone",
        entity_id=zone_id,
        new_value=body.model_dump(exclude_none=True, mode="json"),
    )
    return ApiResponse(data=svc.to_dict(zone))


@router.delete("/{zone_id}", response_model=ApiResponse[None], summary="Delete zone")
async def delete_zone(
    zone_id: UUID,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN")),
    svc: ZoneService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_zone(zone_id, UUID(user.enterprise_id))
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="ZONE_DELETED",
        entity_type="zone",
        entity_id=zone_id,
    )
    return ApiResponse(data=None)
