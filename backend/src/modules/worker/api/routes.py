from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.worker.api.schemas import HeartbeatRequest, WorkerResponse
from src.modules.worker.application.services import WorkerService
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import (
    AuthUser,
    WorkerContext,
    get_current_user,
    get_worker_context,
    require_roles,
)

router = APIRouter(prefix="/workers", tags=["Workers"])


def _get_service(db: AsyncSession = Depends(get_db)) -> WorkerService:
    return WorkerService(WorkerRepository(db))


@router.get("", response_model=ApiResponse[list[WorkerResponse]], summary="List all workers")
async def list_workers(
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")),
    svc: WorkerService = Depends(_get_service),
):
    from uuid import UUID as _UUID
    workers = await svc.list_workers(_UUID(user.enterprise_id))
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
    from uuid import UUID as _UUID
    worker = await svc.heartbeat(
        enterprise_id=_UUID(ctx.enterprise_id),
        worker_id=body.worker_id,
        hostname=body.hostname,
        model_version=body.model_version,
        gpu_available=body.gpu_available,
    )
    return ApiResponse(data=_to_response(worker))


@router.get(
    "/{worker_id}/cameras",
    response_model=ApiResponse[list],
    summary="Get cameras + zone configs assigned to this worker",
)
async def get_worker_cameras(
    worker_id: str,
    ctx: WorkerContext = Depends(get_worker_context),
    svc: WorkerService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    cameras = await svc.get_worker_cameras_by_business_id(worker_id, db)
    return ApiResponse(data=cameras)


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
    }
