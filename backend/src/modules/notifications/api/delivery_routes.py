"""Tenant-administrator delivery monitoring and explicit recovery."""
import math
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, VisionGuardException
from src.core.settings import settings
from src.shared.database.models import Alert, AuditLog, Enterprise, NotificationDelivery, User
from src.shared.database.pid import to_pk
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, require_roles

router = APIRouter(prefix="/notifications/deliveries", tags=["Notification Delivery"])
admin = require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")
DeliveryStatus = Literal["Pending", "Retrying", "Sent", "Published", "Failed", "Skipped"]


def response_row(job, alert_id):
    return {"id": job.public_id, "alert_id": alert_id, "alert_number": job.payload.get("alert_number"), "channel": job.channel,
        "status": job.status, "attempts": job.attempts, "max_attempts": job.max_attempts,
        "next_attempt_at": job.next_attempt_at, "delivered_at": job.delivered_at,
        "last_error": job.last_error, "created_at": job.created_at}


@router.get("", response_model=ApiResponse[list])
async def list_deliveries(
    status: DeliveryStatus | None = None, alert_id: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    user: AuthUser = Depends(admin), db: AsyncSession = Depends(get_db),
):
    enterprise_pk = await to_pk(db, Enterprise, user.enterprise_id)
    query = select(NotificationDelivery, Alert.public_id).join(Alert, Alert.id == NotificationDelivery.alert_id).where(
        NotificationDelivery.enterprise_id == enterprise_pk, Alert.enterprise_id == enterprise_pk)
    if status:
        query = query.where(NotificationDelivery.status == status)
    if alert_id:
        query = query.where(Alert.public_id == alert_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    return ApiResponse(data=[response_row(job, public_id) for job, public_id in rows],
        meta=MetaResponse(page=page, page_size=page_size, total=total, total_pages=max(1, math.ceil(total / page_size))))


@router.get("/summary", response_model=ApiResponse[dict])
async def summary(user: AuthUser = Depends(admin), db: AsyncSession = Depends(get_db)):
    enterprise_pk = await to_pk(db, Enterprise, user.enterprise_id)
    counts = (await db.execute(select(NotificationDelivery.status, func.count()).where(
        NotificationDelivery.enterprise_id == enterprise_pk).group_by(NotificationDelivery.status))).all()
    oldest = await db.scalar(select(func.min(NotificationDelivery.created_at)).where(
        NotificationDelivery.enterprise_id == enterprise_pk, NotificationDelivery.status.in_(["Pending", "Retrying"])))
    return ApiResponse(data={"counts": dict(counts), "oldest_pending_at": oldest})


@router.post("/{delivery_id}/retry", response_model=ApiResponse[dict])
async def retry_delivery(delivery_id: str, user: AuthUser = Depends(admin), db: AsyncSession = Depends(get_db)):
    enterprise_pk = await to_pk(db, Enterprise, user.enterprise_id)
    job = await db.scalar(select(NotificationDelivery).where(
        NotificationDelivery.public_id == delivery_id, NotificationDelivery.enterprise_id == enterprise_pk).with_for_update())
    if job is None:
        raise NotFoundException("NotificationDelivery", delivery_id)
    if job.status not in {"Failed", "Skipped"}:
        raise VisionGuardException(code="DELIVERY_NOT_RETRYABLE", message="Only failed or skipped deliveries can be retried", status_code=409)
    old_status = job.status
    job.status = "Pending"
    job.max_attempts = job.attempts + settings.NOTIFY_RETRY_ATTEMPTS
    job.next_attempt_at = func.now()
    job.last_error = None
    job.updated_by = user.user_id
    db.add(AuditLog(enterprise_id=enterprise_pk, user_id=await to_pk(db, User, user.user_id),
        action="NOTIFICATION_RETRY_REQUESTED", entity_type="notification_delivery", entity_id=job.public_id,
        old_value={"status": old_status}, new_value={"status": "Pending", "max_attempts": job.max_attempts}))
    await db.commit()
    return ApiResponse(data={"id": job.public_id, "status": job.status})
