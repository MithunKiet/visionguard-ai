from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.camera.api.schemas import (
    CameraHealthResponse,
    CameraResponse,
    CreateCameraRequest,
    RtspTestResponse,
    TestConnectionRequest,
    UpdateCameraRequest,
    UpdateCameraStatusRequest,
)
from src.modules.camera.application.services import CameraService
from src.modules.camera.infrastructure.repositories import CameraRepository
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.scope import get_scope

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _get_service(db: AsyncSession = Depends(get_db)) -> CameraService:
    return CameraService(CameraRepository(db), WorkerRepository(db))


@router.get("", response_model=ApiResponse[list[CameraResponse]], summary="List cameras")
async def list_cameras(
    factory_id: str | None = None,
    zone_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    cameras = await svc.list_cameras(
        user.enterprise_id, factory_id, zone_id, get_scope(user)
    )
    # Batched — one pair of queries for every camera's zone config instead
    # of resolve_enforced_ppe's own 2 queries called once per camera.
    enforced_by_camera = await svc.resolve_enforced_ppe_batch(cameras, db)
    return ApiResponse(data=[_to_response_precomputed(c, enforced_by_camera[c.id]) for c in cameras])


@router.post("", response_model=ApiResponse[CameraResponse], summary="Add camera")
async def create_camera(
    body: CreateCameraRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")),
    svc: CameraService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    camera = await svc.create_camera(
        enterprise_id=user.enterprise_id,
        zone_id=body.zone_id,
        name=body.name,
        code=body.code,
        rtsp_url=body.rtsp_url,
        db=db,
        camera_type=body.camera_type,
        position_desc=body.position_desc,
        fps=body.fps,
        ppe_overrides=body.ppe_overrides,
    )
    return ApiResponse(data=await _to_response(camera, svc, db))


@router.get("/{camera_id}", response_model=ApiResponse[CameraResponse], summary="Get camera")
async def get_camera(
    camera_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    camera = await svc.get_camera(camera_id, user.enterprise_id, get_scope(user))
    return ApiResponse(data=await _to_response(camera, svc, db))


@router.put("/{camera_id}", response_model=ApiResponse[CameraResponse], summary="Update camera")
async def update_camera(
    camera_id: str,
    body: UpdateCameraRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")),
    svc: CameraService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    camera = await svc.update_camera(
        camera_id,
        user.enterprise_id,
        scope=get_scope(user),
        **body.model_dump(exclude_none=True),
    )
    return ApiResponse(data=await _to_response(camera, svc, db))


@router.patch("/{camera_id}/status", response_model=ApiResponse[CameraResponse], summary="Turn camera on/off")
async def set_camera_status(
    camera_id: str,
    body: UpdateCameraStatusRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")),
    svc: CameraService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    camera = await svc.set_active(camera_id, user.enterprise_id, body.status == "Active", get_scope(user))

    from src.modules.audit.application.services import AuditService
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="CAMERA_STATUS_CHANGED",
        entity_type="camera",
        entity_id=camera_id,
        new_value={"status": body.status},
    )
    return ApiResponse(data=await _to_response(camera, svc, db))


@router.delete("/{camera_id}", response_model=ApiResponse[None], summary="Delete camera")
async def delete_camera(
    camera_id: str,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
    svc: CameraService = Depends(_get_service),
):
    await svc.delete_camera(camera_id, user.enterprise_id, get_scope(user))
    return ApiResponse(data=None)


@router.post(
    "/test-connection",
    response_model=ApiResponse[RtspTestResponse],
    summary="Test RTSP connection",
)
async def test_connection(
    body: TestConnectionRequest,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
):
    result = await svc.test_rtsp_connection(body.rtsp_url)
    return ApiResponse(data=result)


@router.get(
    "/{camera_id}/health",
    response_model=ApiResponse[CameraHealthResponse],
    summary="Camera health check",
)
async def camera_health(
    camera_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
):
    health = await svc.get_camera_health(camera_id, user.enterprise_id, get_scope(user))
    return ApiResponse(data=health)


async def _to_response(c, svc: CameraService, db: AsyncSession) -> dict:
    return _to_response_precomputed(c, await svc.resolve_enforced_ppe(c, db))


def _to_response_precomputed(c, enforces: list[str]) -> dict:
    return {
        "id": c.id,
        "enterprise_id": c.enterprise_id,
        "factory_id": c.factory_id,
        "zone_id": c.zone_id,
        "worker_id": c.worker_id,
        "name": c.name,
        "code": c.code,
        "rtsp_url": c.rtsp_url,
        "camera_type": c.camera_type,
        "position_desc": c.position_desc,
        "status": c.status,
        "fps": c.fps,
        "in_maintenance": c.in_maintenance,
        "last_seen_at": c.last_seen_at,
        "ppe_overrides": c.ppe_overrides,
        "enforces": enforces,
    }
