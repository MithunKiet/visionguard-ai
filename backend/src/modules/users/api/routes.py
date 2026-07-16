from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.api.schemas import InviteUserRequest, UpdateUserRequest
from src.modules.users.application.services import UserManagementService
from src.modules.users.infrastructure.repositories import UserAdminRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, require_roles
from src.shared.security.scope import get_scope

router = APIRouter(prefix="/users", tags=["User Management"])

_MANAGE_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> UserManagementService:
    return UserManagementService(UserAdminRepository(db), db)


@router.get("", response_model=ApiResponse[list], summary="List users in your enterprise")
async def list_users(
    user: AuthUser = Depends(require_roles(*_MANAGE_ROLES)),
    svc: UserManagementService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_users(user.enterprise_id, get_scope(user)))


@router.post("", response_model=ApiResponse[dict], summary="Invite a new user")
async def invite_user(
    body: InviteUserRequest,
    user: AuthUser = Depends(require_roles(*_MANAGE_ROLES)),
    svc: UserManagementService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.invite_user(
        enterprise_id=user.enterprise_id,
        invited_by=user.user_id,
        caller_roles=user.roles,
        caller_factory_id=user.factory_id,
        name=body.name,
        email=body.email,
        roles=body.roles,
        factory_id=body.factory_id,
        department_id=body.department_id,
        assigned_zone_ids=body.assigned_zone_ids,
    )
    from src.modules.audit.application.services import AuditService
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="USER_INVITED",
        entity_type="user",
        entity_id=result["id"],
        new_value={"email": body.email, "roles": body.roles},
    )
    return ApiResponse(data=result)


@router.get("/{user_id}", response_model=ApiResponse[dict], summary="Get user detail")
async def get_user(
    user_id: str,
    user: AuthUser = Depends(require_roles(*_MANAGE_ROLES)),
    svc: UserManagementService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_user(user_id, user.enterprise_id, get_scope(user)))


@router.put("/{user_id}", response_model=ApiResponse[dict], summary="Update a user")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    user: AuthUser = Depends(require_roles(*_MANAGE_ROLES)),
    svc: UserManagementService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.update_user(
        user_id, user.enterprise_id, user.roles, user.factory_id, get_scope(user),
        **body.model_dump(exclude_unset=True),
    )
    from src.modules.audit.application.services import AuditService
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="USER_UPDATED",
        entity_type="user",
        entity_id=user_id,
        new_value=body.model_dump(exclude_unset=True, mode="json"),
    )
    return ApiResponse(data=result)


@router.delete("/{user_id}", response_model=ApiResponse[None], summary="Deactivate a user")
async def deactivate_user(
    user_id: str,
    user: AuthUser = Depends(require_roles(*_MANAGE_ROLES)),
    svc: UserManagementService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    await svc.deactivate_user(user_id, user.enterprise_id, get_scope(user))
    from src.modules.audit.application.services import AuditService
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="USER_DEACTIVATED",
        entity_type="user",
        entity_id=user_id,
    )
    return ApiResponse(data=None)
