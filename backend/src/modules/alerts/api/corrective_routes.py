"""Incident corrective workflow, including bounded authenticated photo transfers."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.formparsers import MultiPartException
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.modules.alerts.api.schemas import CompleteActionRequest, CorrectivePlanRequest
from src.modules.alerts.application.corrective import CorrectiveActionService, MAX_PHOTO_BYTES, REVIEW_ROLES
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.resource_policy import enforce_resource_scope


class EvidenceUploadRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def bounded(request: Request):
            if request.method != "POST" or not request.url.path.endswith("/corrective-action/evidence"):
                return await original(request)
            received, exceeded = 0, False
            async def receive():
                nonlocal received, exceeded
                message = await request.receive()
                received += len(message.get("body", b""))
                if received > MAX_PHOTO_BYTES + 1024 * 1024:
                    exceeded = True
                    # MultipartParser closes temporary files on this exception.
                    raise MultiPartException("Evidence upload is too large")
                return message
            try:
                return await original(Request(request.scope, receive=receive))
            except StarletteHTTPException:
                if exceeded:
                    raise HTTPException(413, "Evidence upload exceeds 6 MiB including form fields")
                raise
        return bounded


router = APIRouter(prefix="/alerts", tags=["Corrective actions"], route_class=EvidenceUploadRoute,
                   dependencies=[Depends(enforce_resource_scope)])


@router.get("/{alert_id}/corrective-action", response_model=ApiResponse[dict])
async def action_detail(alert_id: UUID, user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await CorrectiveActionService(db, user).get(str(alert_id)))


@router.get("/{alert_id}/assignees", response_model=ApiResponse[list])
async def assignees(alert_id: UUID, search: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1000000),
                    page_size: int = Query(20, ge=1, le=100), user: AuthUser = Depends(require_roles(*REVIEW_ROLES)),
                    db: AsyncSession = Depends(get_db)):
    rows, total = await CorrectiveActionService(db, user).assignees(str(alert_id), search, page, page_size)
    return ApiResponse(data=rows, meta=MetaResponse(page=page, page_size=page_size, total=total,
        total_pages=max(1, (total + page_size - 1) // page_size)))


@router.put("/{alert_id}/corrective-action", response_model=ApiResponse[dict])
async def save_action(alert_id: UUID, body: CorrectivePlanRequest, user: AuthUser = Depends(require_roles(*REVIEW_ROLES)),
                      db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await CorrectiveActionService(db, user).plan(str(alert_id), body))


@router.post("/{alert_id}/corrective-action/complete", response_model=ApiResponse[dict])
async def complete_action(alert_id: UUID, body: CompleteActionRequest, user: AuthUser = Depends(require_roles(*REVIEW_ROLES)),
                          db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await CorrectiveActionService(db, user).complete(str(alert_id), body))


@router.post("/{alert_id}/corrective-action/evidence", response_model=ApiResponse[dict])
async def upload_evidence(alert_id: UUID, expected_revision: int = Form(..., ge=0), upload_id: UUID = Form(...),
                          file: UploadFile = File(...), user: AuthUser = Depends(require_roles(*REVIEW_ROLES)),
                          db: AsyncSession = Depends(get_db)):
    try:
        content = await file.read(MAX_PHOTO_BYTES + 1)
        return ApiResponse(data=await CorrectiveActionService(db, user).upload(str(alert_id), expected_revision,
            str(upload_id), file.filename, content))
    finally:
        await file.close()


@router.get("/{alert_id}/corrective-action/evidence/{evidence_id}")
async def download_evidence(alert_id: UUID, evidence_id: UUID, user: AuthUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    content, content_type = await CorrectiveActionService(db, user).photo(str(alert_id), str(evidence_id))
    extension = "jpg" if content_type == "image/jpeg" else "png"
    return Response(content, media_type=content_type, headers={"Cache-Control": "no-store", "Vary": "Authorization",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'",
        "Content-Disposition": f'attachment; filename="corrective-{evidence_id}.{extension}"'})
