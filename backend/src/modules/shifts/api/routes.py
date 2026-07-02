from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.shifts.api.schemas import CreateShiftRequest, UpdateShiftRequest
from src.modules.shifts.application.services import ShiftService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/shifts", tags=["Shifts"])

_ADMIN_ROLES = ("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ShiftService:
    return ShiftService(db)


@router.get("", response_model=ApiResponse[list], summary="List shifts")
async def list_shifts(
    factory_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: ShiftService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_shifts(UUID(user.enterprise_id), factory_id))


@router.get("/active", response_model=ApiResponse[list], summary="Shifts active right now")
async def active_shifts(
    user: AuthUser = Depends(get_current_user),
    svc: ShiftService = Depends(_get_service),
):
    return ApiResponse(
        data=await svc.active_shifts(UUID(user.enterprise_id), datetime.now(timezone.utc))
    )


@router.post("", response_model=ApiResponse[dict], summary="Create shift")
async def create_shift(
    body: CreateShiftRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ShiftService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_shift(
        UUID(user.enterprise_id), body.factory_id, body.name,
        body.start_time, body.end_time, body.validated_days(),
    ))


@router.put("/{shift_id}", response_model=ApiResponse[dict], summary="Update shift")
async def update_shift(
    shift_id: UUID,
    body: UpdateShiftRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ShiftService = Depends(_get_service),
):
    return ApiResponse(data=await svc.update_shift(
        shift_id, UUID(user.enterprise_id), body.model_dump()
    ))


@router.delete("/{shift_id}", response_model=ApiResponse[None], summary="Deactivate shift")
async def delete_shift(
    shift_id: UUID,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: ShiftService = Depends(_get_service),
):
    await svc.delete_shift(shift_id, UUID(user.enterprise_id))
    return ApiResponse(data=None)
