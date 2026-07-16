from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.factory.api.schemas import CreateFactoryRequest, UpdateFactoryRequest
from src.modules.factory.application.services import FactoryService
from src.modules.factory.infrastructure.repositories import FactoryRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.scope import get_scope

router = APIRouter(prefix="/factories", tags=["Factories"])

_ADMIN_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")


def _get_service(db: AsyncSession = Depends(get_db)) -> FactoryService:
    return FactoryService(FactoryRepository(db))


@router.get("", response_model=ApiResponse[list], summary="List factories")
async def list_factories(
    user: AuthUser = Depends(get_current_user),
    svc: FactoryService = Depends(_get_service),
):
    factories = await svc.list_factories(user.enterprise_id, get_scope(user))
    return ApiResponse(data=[svc.to_dict(f) for f in factories])


@router.post("", response_model=ApiResponse[dict], summary="Create factory")
async def create_factory(
    body: CreateFactoryRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: FactoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    factory = await svc.create_factory(
        user.enterprise_id, body.name, body.code, body.location, body.plant_head_id
    )
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="FACTORY_CREATED",
        entity_type="factory",
        entity_id=factory.id,
        new_value=svc.to_dict(factory),
    )
    return ApiResponse(data=svc.to_dict(factory))


@router.get("/{factory_id}", response_model=ApiResponse[dict], summary="Get factory")
async def get_factory(
    factory_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: FactoryService = Depends(_get_service),
):
    factory = await svc.get_factory(factory_id, user.enterprise_id)
    return ApiResponse(data=svc.to_dict(factory))


@router.put("/{factory_id}", response_model=ApiResponse[dict], summary="Update factory")
async def update_factory(
    factory_id: str,
    body: UpdateFactoryRequest,
    user: AuthUser = Depends(require_roles(*_ADMIN_ROLES)),
    svc: FactoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    factory = await svc.update_factory(
        factory_id, user.enterprise_id, **body.model_dump(exclude_none=True)
    )
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="FACTORY_UPDATED",
        entity_type="factory",
        entity_id=factory_id,
        new_value=body.model_dump(exclude_none=True, mode="json"),
    )
    return ApiResponse(data=svc.to_dict(factory))


@router.delete("/{factory_id}", response_model=ApiResponse[None], summary="Delete factory")
async def delete_factory(
    factory_id: str,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
    svc: FactoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_factory(factory_id, user.enterprise_id)
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="FACTORY_DELETED",
        entity_type="factory",
        entity_id=factory_id,
    )
    return ApiResponse(data=None)
