import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.alerts.api.schemas import (
    AcknowledgeRequest,
    AssignRequest,
    FalsePositiveRequest,
    ResolveRequest,
)
from src.modules.alerts.application.services import AlertService
from src.modules.alerts.infrastructure.repositories import AlertRepository
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _get_service(db: AsyncSession = Depends(get_db)) -> AlertService:
    return AlertService(AlertRepository(db))


async def _audit(db: AsyncSession, user: AuthUser, action: str, alert_id: UUID, detail: dict | None = None) -> None:
    from src.modules.audit.application.services import AuditService
    await AuditService(db).record(
        enterprise_id=UUID(user.enterprise_id),
        user_id=UUID(user.user_id),
        action=action,
        entity_type="alert",
        entity_id=alert_id,
        new_value=detail,
    )


@router.get("", response_model=ApiResponse[list], summary="List alerts")
async def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    zone_id: UUID | None = None,
    assigned_to: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
    svc: AlertService = Depends(_get_service),
):
    items, total = await svc.list_alerts(
        UUID(user.enterprise_id), status, severity, zone_id, assigned_to, page, page_size
    )
    return ApiResponse(
        data=items,
        meta=MetaResponse(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 1,
        ),
    )


@router.get("/{alert_id}", response_model=ApiResponse[dict], summary="Get alert detail")
async def get_alert(
    alert_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: AlertService = Depends(_get_service),
):
    return ApiResponse(data=await svc.get_alert(alert_id, UUID(user.enterprise_id)))


@router.patch("/{alert_id}/acknowledge", response_model=ApiResponse[dict])
async def acknowledge_alert(
    alert_id: UUID,
    _body: AcknowledgeRequest = AcknowledgeRequest(),
    user: AuthUser = Depends(require_roles("SAFETY_OFFICER", "FACTORY_MANAGER", "SUPER_ADMIN")),
    svc: AlertService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.acknowledge(alert_id, UUID(user.enterprise_id), UUID(user.user_id))
    await _audit(db, user, "ALERT_ACKNOWLEDGED", alert_id)
    return ApiResponse(data=data)


@router.patch("/{alert_id}/resolve", response_model=ApiResponse[dict])
async def resolve_alert(
    alert_id: UUID,
    body: ResolveRequest,
    user: AuthUser = Depends(require_roles("SAFETY_OFFICER", "FACTORY_MANAGER", "SUPER_ADMIN")),
    svc: AlertService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.resolve(alert_id, UUID(user.enterprise_id), UUID(user.user_id), body.note)
    await _audit(db, user, "ALERT_RESOLVED", alert_id, {"note": body.note})
    return ApiResponse(data=data)


@router.patch("/{alert_id}/false-positive", response_model=ApiResponse[dict])
async def false_positive_alert(
    alert_id: UUID,
    body: FalsePositiveRequest,
    user: AuthUser = Depends(require_roles("SAFETY_OFFICER", "FACTORY_MANAGER", "SUPER_ADMIN")),
    svc: AlertService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.mark_false_positive(
        alert_id, UUID(user.enterprise_id), UUID(user.user_id), body.reason
    )
    await _audit(db, user, "ALERT_FALSE_POSITIVE", alert_id, {"reason": body.reason})
    return ApiResponse(data=data)


@router.patch("/{alert_id}/assign", response_model=ApiResponse[dict])
async def assign_alert(
    alert_id: UUID,
    body: AssignRequest,
    user: AuthUser = Depends(require_roles("FACTORY_MANAGER", "SUPER_ADMIN")),
    svc: AlertService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    data = await svc.assign(alert_id, UUID(user.enterprise_id), body.user_id)
    await _audit(db, user, "ALERT_ASSIGNED", alert_id, {"assigned_to": str(body.user_id)})
    return ApiResponse(data=data)
