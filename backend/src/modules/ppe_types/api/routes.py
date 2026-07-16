from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ppe_types.api.schemas import CreatePpeTypeRequest, UpdatePpeTypeRequest
from src.modules.ppe_types.application.services import PpeTypeService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/ppe-types", tags=["PPE Types"])

_ADMIN_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> PpeTypeService:
    return PpeTypeService(db)


@router.get("", response_model=ApiResponse[list], summary="List PPE types")
async def list_ppe_types(
    include_inactive: bool = False,
    user: AuthUser = Depends(get_current_user),
    svc: PpeTypeService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_types(user.enterprise_id, include_inactive))


@router.post("", response_model=ApiResponse[dict], summary="Add a PPE type")
async def create_ppe_type(
    body: CreatePpeTypeRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: PpeTypeService = Depends(_get_service),
):
    return ApiResponse(data=await svc.create_type(
        user.enterprise_id, body.name, user.user_id,
    ))


@router.patch("/{type_id}", response_model=ApiResponse[dict], summary="Rename or activate/deactivate a PPE type")
async def update_ppe_type(
    type_id: str,
    body: UpdatePpeTypeRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: PpeTypeService = Depends(_get_service),
):
    return ApiResponse(data=await svc.update_type(
        type_id, user.enterprise_id, body.name, body.is_active,
    ))
