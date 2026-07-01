from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.camera.api.schemas import (
    CameraHealthResponse,
    CameraResponse,
    CreateCameraRequest,
    RtspTestResponse,
    TestConnectionRequest,
    UpdateCameraRequest,
)
from src.modules.camera.application.services import CameraService
from src.modules.camera.infrastructure.repositories import CameraRepository
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _get_service(db: AsyncSession = Depends(get_db)) -> CameraService:
    return CameraService(CameraRepository(db), WorkerRepository(db))


@router.get("", response_model=ApiResponse[list[CameraResponse]], summary="List cameras")
async def list_cameras(
    factory_id: UUID | None = None,
    zone_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    cameras = await svc.list_cameras(
        _UUID(user.enterprise_id), factory_id, zone_id
    )
    return ApiResponse(data=[_to_response(c) for c in cameras])


@router.post("", response_model=ApiResponse[CameraResponse], summary="Add camera")
async def create_camera(
    body: CreateCameraRequest,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    camera = await svc.create_camera(
        enterprise_id=_UUID(user.enterprise_id),
        factory_id=body.factory_id,
        zone_id=body.zone_id,
        name=body.name,
        code=body.code,
        rtsp_url=body.rtsp_url,
        camera_type=body.camera_type,
        position_desc=body.position_desc,
        fps=body.fps,
    )
    return ApiResponse(data=_to_response(camera))


@router.get("/{camera_id}", response_model=ApiResponse[CameraResponse], summary="Get camera")
async def get_camera(
    camera_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    camera = await svc.get_camera(camera_id, _UUID(user.enterprise_id))
    return ApiResponse(data=_to_response(camera))


@router.put("/{camera_id}", response_model=ApiResponse[CameraResponse], summary="Update camera")
async def update_camera(
    camera_id: UUID,
    body: UpdateCameraRequest,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    camera = await svc.update_camera(
        camera_id,
        _UUID(user.enterprise_id),
        **body.model_dump(exclude_none=True),
    )
    return ApiResponse(data=_to_response(camera))


@router.delete("/{camera_id}", response_model=ApiResponse[None], summary="Delete camera")
async def delete_camera(
    camera_id: UUID,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN")),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    await svc.delete_camera(camera_id, _UUID(user.enterprise_id))
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
    camera_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: CameraService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    health = await svc.get_camera_health(camera_id, _UUID(user.enterprise_id))
    return ApiResponse(data=health)


def _to_response(c) -> dict:
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
    }
