from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.api.schemas import AddRecipientRequest
from src.modules.notifications.application.services import NotificationService
from src.modules.notifications.infrastructure.repositories import NotificationRecipientRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/notifications/recipients", tags=["Notification Recipients"])


def _get_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(NotificationRecipientRepository(db), db)


@router.get("", response_model=ApiResponse[list], summary="List configured notification recipients")
async def list_recipients(
    zone_id: UUID | None = None,
    user: AuthUser = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list_recipients(UUID(user.enterprise_id), zone_id))


@router.post(
    "", response_model=ApiResponse[dict],
    summary="Add a recipient — who gets emailed/desktop-notified for a zone's violations",
)
async def add_recipient(
    body: AddRecipientRequest,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")),
    svc: NotificationService = Depends(_get_service),
):
    return ApiResponse(data=await svc.add_recipient(
        UUID(user.enterprise_id), body.user_id, body.zone_id,
        body.level, body.notify_email, body.notify_desktop,
    ))


@router.delete("/{recipient_id}", response_model=ApiResponse[dict], summary="Remove a recipient")
async def remove_recipient(
    recipient_id: UUID,
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER")),
    svc: NotificationService = Depends(_get_service),
):
    await svc.remove_recipient(recipient_id, UUID(user.enterprise_id))
    return ApiResponse(data={"deleted": True})
