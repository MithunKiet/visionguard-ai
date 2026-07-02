from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.maintenance.api.schemas import (
    CompleteMaintenanceRequest,
    EnableMaintenanceModeRequest,
    ScheduleMaintenanceRequest,
)
from src.modules.maintenance.application.services import MaintenanceService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])

_ADMIN_ROLES = ("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> MaintenanceService:
    return MaintenanceService(db)


@router.get("", response_model=ApiResponse[list], summary="List maintenance records")
async def list_maintenance(
    camera_id: UUID | None = None,
    status: str | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: MaintenanceService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list(UUID(user.enterprise_id), camera_id, status))


@router.post("", response_model=ApiResponse[dict], summary="Schedule camera maintenance")
async def schedule_maintenance(
    body: ScheduleMaintenanceRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: MaintenanceService = Depends(_get_service),
):
    return ApiResponse(data=await svc.schedule(
        UUID(user.enterprise_id), body.camera_id, body.scheduled_date,
        body.maintenance_type, body.assigned_to, body.notes,
    ))


@router.patch("/{maintenance_id}/complete", response_model=ApiResponse[dict], summary="Complete maintenance")
async def complete_maintenance(
    maintenance_id: UUID,
    body: CompleteMaintenanceRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: MaintenanceService = Depends(_get_service),
):
    return ApiResponse(data=await svc.complete(
        maintenance_id, UUID(user.enterprise_id), UUID(user.user_id),
        body.completion_notes, body.next_due_date,
    ))


@router.post("/camera/{camera_id}/enable", response_model=ApiResponse[dict], summary="Enable maintenance mode (suppresses alerts)")
async def enable_maintenance_mode(
    camera_id: UUID,
    body: EnableMaintenanceModeRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: MaintenanceService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.enable_mode(camera_id, UUID(user.enterprise_id), body.until)
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="CAMERA_MAINTENANCE_ENABLED",
        entity_type="camera",
        entity_id=camera_id,
        new_value={"until": body.until.isoformat() if body.until else None, "reason": body.reason},
    )
    return ApiResponse(data=data)


@router.post("/camera/{camera_id}/disable", response_model=ApiResponse[dict], summary="Disable maintenance mode")
async def disable_maintenance_mode(
    camera_id: UUID,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: MaintenanceService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.disable_mode(camera_id, UUID(user.enterprise_id))
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="CAMERA_MAINTENANCE_DISABLED",
        entity_type="camera",
        entity_id=camera_id,
    )
    return ApiResponse(data=data)
