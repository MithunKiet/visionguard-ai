from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.modules.enterprise.api.schemas import CreateEnterpriseRequest, UpdateBrandingRequest
from src.modules.enterprise.application.services import EnterpriseService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])

# Separate router/prefix: "/enterprise/*" above manages the caller's own
# enterprise (branding); "/enterprises/*" here is the SYSTEM_ADMIN-only,
# cross-tenant master for onboarding new client enterprises.
enterprises_router = APIRouter(prefix="/enterprises", tags=["Enterprises"])


def _get_service(db: AsyncSession = Depends(get_db)) -> EnterpriseService:
    return EnterpriseService(db)


@router.get("/branding", response_model=ApiResponse[dict], summary="Get enterprise branding")
async def get_branding(
    user: AuthUser = Depends(get_current_user),
    svc: EnterpriseService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_branding(user.enterprise_id))


@router.put("/branding", response_model=ApiResponse[dict], summary="Update enterprise branding")
async def update_branding(
    body: UpdateBrandingRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
    svc: EnterpriseService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.update_branding(user.enterprise_id, body.model_dump())
    await AuditService(db).record(
        enterprise_id=user.enterprise_id,
        user_id=user.user_id,
        action="BRANDING_UPDATED",
        entity_type="enterprise",
        entity_id=user.enterprise_id,
        new_value=body.model_dump(exclude_none=True),
    )
    return ApiResponse(data=data)


@enterprises_router.get("", response_model=ApiResponse[list], summary="List all enterprises (platform-wide)")
async def list_enterprises(
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN")),
    svc: EnterpriseService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_enterprises())


@enterprises_router.post("", response_model=ApiResponse[dict], summary="Onboard a new enterprise + its first HO Admin")
async def create_enterprise(
    body: CreateEnterpriseRequest,
    user: AuthUser = Depends(require_roles("SYSTEM_ADMIN")),
    svc: EnterpriseService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.create_enterprise(
        body.name, body.code, body.admin_name, body.admin_email, user.user_id,
        industry=body.industry, contact_person=body.contact_person, contact_email=body.contact_email,
        primary_color=body.primary_color, secondary_color=body.secondary_color,
    )
    await AuditService(db).record(
        enterprise_id=result["id"],
        user_id=user.user_id,
        action="ENTERPRISE_CREATED",
        entity_type="enterprise",
        entity_id=result["id"],
        new_value={"name": body.name, "code": body.code, "admin_email": body.admin_email},
    )
    return ApiResponse(data=result)
