from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.onboarding.api.schemas import (
    SetupCameraRequest,
    SetupDepartmentRequest,
    SetupFactoryRequest,
    SetupZoneRequest,
)
from src.modules.onboarding.application.services import SetupWizardService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, require_roles

router = APIRouter(prefix="/setup", tags=["Setup Wizard"])

_SETUP_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")


def _get_service(db: AsyncSession = Depends(get_db)) -> SetupWizardService:
    return SetupWizardService(db)


@router.get("/progress", response_model=ApiResponse[dict], summary="Get setup wizard progress")
async def get_progress(
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_progress(user.user_id, user.enterprise_id))


@router.post("/factory", response_model=ApiResponse[dict], summary="Step 1 — create factory")
async def setup_factory(
    body: SetupFactoryRequest,
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_factory(
        user.user_id, user.enterprise_id, body.name, body.code, body.location
    ))


@router.post("/department", response_model=ApiResponse[dict], summary="Step 2 — create department")
async def setup_department(
    body: SetupDepartmentRequest,
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_department(
        user.user_id, user.enterprise_id, body.name, body.code
    ))


@router.post("/zone", response_model=ApiResponse[dict], summary="Step 3 — create zone + PPE config")
async def setup_zone(
    body: SetupZoneRequest,
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_zone(
        user.user_id, user.enterprise_id, body.name, body.code,
        body.max_occupancy, body.zone_type, body.is_restricted,
        required_ppe_types=body.required_ppe_types,
    ))


@router.post("/camera", response_model=ApiResponse[dict], summary="Step 4 — add camera")
async def setup_camera(
    body: SetupCameraRequest,
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_camera(
        user.user_id, user.enterprise_id, body.name, body.code,
        body.rtsp_url, body.camera_type, body.position_desc, body.placement_confirmed,
    ))


@router.post("/complete", response_model=ApiResponse[dict], summary="Finish setup wizard")
async def setup_complete(
    user: AuthUser = Depends(require_roles(*_SETUP_ROLES)),
    svc: SetupWizardService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.complete(user.user_id, user.enterprise_id)
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="SETUP_COMPLETED",
        entity_type="setup_progress",
        new_value=data,
    )
    return ApiResponse(data=data)
