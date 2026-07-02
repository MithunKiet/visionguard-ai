import math
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.audit.application.services import AuditService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, require_roles

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=ApiResponse[list], summary="Query the immutable audit trail")
async def list_audit(
    action: str | None = None,
    user_id: UUID | None = None,
    entity_type: str | None = None,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN", "SAFETY_OFFICER")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuditService(db).list(
        UUID(user.enterprise_id), action, user_id, entity_type, from_dt, to_dt, page, page_size
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
