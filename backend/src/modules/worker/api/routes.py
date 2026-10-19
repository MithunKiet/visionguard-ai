
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.worker.api.schemas import ConfigApplicationsRequest, HeartbeatRequest, WorkerResponse, WorkerSchedulingRequest
from src.modules.worker.application.services import WorkerService
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.modules.worker.infrastructure.scheduling import WorkerSchedulingRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import (
    AuthUser,
    WorkerContext,
    get_worker_context,
    require_roles,
)

router = APIRouter(prefix="/workers", tags=["Workers"])


def _get_service(db: AsyncSession = Depends(get_db)) -> WorkerService:
    return WorkerService(WorkerRepository(db))


@router.get("", response_model=ApiResponse[list[WorkerResponse]], summary="List all workers")
async def list_workers(
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
    svc: WorkerService = Depends(_get_service),
):
    workers = await svc.list_workers(user.enterprise_id)
    return ApiResponse(data=[_to_response(w) for w in workers])


@router.post(
    "/heartbeat",
    response_model=ApiResponse[WorkerResponse],
    summary="AI Worker heartbeat — auto-registers on first call",
)
async def heartbeat(
    body: HeartbeatRequest,
    ctx: WorkerContext = Depends(get_worker_context),
    svc: WorkerService = Depends(_get_service),
):
    if ctx.worker_id and ctx.worker_id != body.worker_id:
        from src.core.exceptions import ForbiddenException
        raise ForbiddenException("Worker identity mismatch")
    worker = await svc.heartbeat(
        enterprise_id=ctx.enterprise_id,
        worker_id=body.worker_id,
        hostname=body.hostname,
        model_version=body.model_version,
        gpu_available=body.gpu_available,
    )
    return ApiResponse(data=_to_response(worker))


@router.put("/{worker_public_id}/scheduling", response_model=ApiResponse[WorkerResponse],
            summary="Set a worker's allowed factory and measured camera limit")
async def configure_worker_scheduling(
    worker_public_id: UUID,
    body: WorkerSchedulingRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    await WorkerSchedulingRepository(db).configure(
        str(worker_public_id), user.enterprise_id, str(body.factory_id), body.max_cameras, user.user_id,
    )
    worker = await WorkerRepository(db).get_by_id(str(worker_public_id))
    return ApiResponse(data=_to_response(worker))


@router.get(
    "/{worker_id}/cameras",
    response_model=ApiResponse[list],
    summary="Get cameras + zone configs assigned to this worker",
)
async def get_worker_cameras(
    worker_id: str,
    x_worker_session: UUID = Header(...),
    ctx: WorkerContext = Depends(get_worker_context),
    svc: WorkerService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    if ctx.worker_id and ctx.worker_id != worker_id:
        from src.core.exceptions import ForbiddenException
        raise ForbiddenException("Worker identity mismatch")
    cameras = await svc.get_worker_cameras_by_business_id(worker_id, db, ctx.enterprise_id, session_id=str(x_worker_session))
    return ApiResponse(data=cameras)


@router.post("/{worker_id}/config-applied", response_model=ApiResponse[dict],
             summary="Confirm installed zone policy under current camera ownership")
async def acknowledge_config_application(
    worker_id: str,
    body: ConfigApplicationsRequest,
    x_worker_session: UUID = Header(...),
    ctx: WorkerContext = Depends(get_worker_context),
    db: AsyncSession = Depends(get_db),
):
    from src.core.exceptions import ForbiddenException
    from src.modules.config.application.application_status import acknowledge_configs
    if ctx.worker_id and ctx.worker_id != worker_id:
        raise ForbiddenException("Worker identity mismatch")
    return ApiResponse(data=await acknowledge_configs(
        db, ctx.enterprise_id, worker_id, str(x_worker_session), body.applications))


def _to_response(w) -> dict:
    return {
        "id": w.id,
        "enterprise_id": w.enterprise_id,
        "worker_id": w.worker_id,
        "hostname": w.hostname,
        "status": w.status,
        "model_version": w.model_version,
        "gpu_available": w.gpu_available,
        "last_heartbeat": w.last_heartbeat,
        "is_alive": w.is_alive,
        "factory_id": w.factory_id,
        "max_cameras": w.max_cameras,
    }
