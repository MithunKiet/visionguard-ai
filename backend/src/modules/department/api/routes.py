from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.department.api.schemas import CreateDepartmentRequest, UpdateDepartmentRequest
from src.modules.department.application.services import DepartmentService
from src.modules.department.infrastructure.repositories import DepartmentRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/departments", tags=["Departments"])

_ADMIN_ROLES = ("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> DepartmentService:
    return DepartmentService(DepartmentRepository(db))


@router.get("", response_model=ApiResponse[list], summary="List departments")
async def list_departments(
    factory_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: DepartmentService = Depends(_get_service),
):
    departments = await svc.list_departments(UUID(user.enterprise_id), factory_id)
    return ApiResponse(data=[svc.to_dict(d) for d in departments])


@router.post("", response_model=ApiResponse[dict], summary="Create department")
async def create_department(
    body: CreateDepartmentRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: DepartmentService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    department = await svc.create_department(
        UUID(user.enterprise_id), body.factory_id, body.name, body.code, body.head_user_id
    )
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="DEPARTMENT_CREATED",
        entity_type="department",
        entity_id=department.id,
        new_value=svc.to_dict(department),
    )
    return ApiResponse(data=svc.to_dict(department))


@router.get("/{department_id}", response_model=ApiResponse[dict], summary="Get department")
async def get_department(
    department_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: DepartmentService = Depends(_get_service),
):
    department = await svc.get_department(department_id, UUID(user.enterprise_id))
    return ApiResponse(data=svc.to_dict(department))


@router.put("/{department_id}", response_model=ApiResponse[dict], summary="Update department")
async def update_department(
    department_id: UUID,
    body: UpdateDepartmentRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: DepartmentService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    department = await svc.update_department(
        department_id, UUID(user.enterprise_id), **body.model_dump(exclude_none=True)
    )
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="DEPARTMENT_UPDATED",
        entity_type="department",
        entity_id=department_id,
        new_value=body.model_dump(exclude_none=True, mode="json"),
    )
    return ApiResponse(data=svc.to_dict(department))


@router.delete("/{department_id}", response_model=ApiResponse[None], summary="Delete department")
async def delete_department(
    department_id: UUID,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN")),
    svc: DepartmentService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_department(department_id, UUID(user.enterprise_id))
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="DEPARTMENT_DELETED",
        entity_type="department",
        entity_id=department_id,
    )
    return ApiResponse(data=None)
