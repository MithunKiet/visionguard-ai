from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.enterprise.api.schemas import UpdateBrandingRequest
from src.modules.enterprise.application.services import EnterpriseService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])


def _get_service(db: AsyncSession = Depends(get_db)) -> EnterpriseService:
    return EnterpriseService(db)


@router.get("/branding", response_model=ApiResponse[dict], summary="Get enterprise branding")
async def get_branding(
    user: AuthUser = Depends(get_current_user),
    svc: EnterpriseService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_branding(UUID(user.enterprise_id)))


@router.put("/branding", response_model=ApiResponse[dict], summary="Update enterprise branding")
async def update_branding(
    body: UpdateBrandingRequest,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN")),
    svc: EnterpriseService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.update_branding(UUID(user.enterprise_id), body.model_dump())
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action="BRANDING_UPDATED",
        entity_type="enterprise",
        entity_id=UUID(user.enterprise_id),
        new_value=body.model_dump(exclude_none=True),
    )
    return ApiResponse(data=data)
