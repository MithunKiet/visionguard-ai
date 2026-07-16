from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.roles.application.services import RoleService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user

router = APIRouter(prefix="/roles", tags=["Roles"])


def _get_service(db: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get("", response_model=ApiResponse[list], summary="List roles (platform-wide catalog)")
async def list_roles(
    include_inactive: bool = False,
    user: AuthUser = Depends(get_current_user),
    svc: RoleService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_roles(include_inactive))
