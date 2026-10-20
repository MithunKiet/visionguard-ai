from src.shared.security.resource_policy import enforce_resource_scope
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reports.api.schemas import GenerateReportRequest
from src.modules.reports.application.services import ReportService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.core.exceptions import ForbiddenException
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.scope import get_scope

router = APIRouter(dependencies=[Depends(enforce_resource_scope)], prefix="/reports", tags=["Reports"])

_REPORT_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    return ReportService(db)


@router.post("/generate", response_model=ApiResponse[dict], status_code=202, summary="Queue a PDF/Excel report")
async def generate_report(
    body: GenerateReportRequest,
    idempotency_key: UUID | None = Header(default=None),
    user: AuthUser = Depends(require_roles(*_REPORT_ROLES)),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report generation requires enterprise-wide scope")
    return ApiResponse(data=await svc.generate(
        user.enterprise_id, user.user_id,
        body.report_type, body.format, body.from_date, body.to_date,
        str(idempotency_key) if idempotency_key else None,
    ))


@router.get("", response_model=ApiResponse[list], summary="List generated reports")
async def list_reports(
    page: int = Query(1, ge=1, le=1_000_000),
    page_size: int = Query(20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report listing requires enterprise-wide scope")
    rows, total = await svc.list(user.enterprise_id, page, page_size)
    return ApiResponse(data=rows, meta=MetaResponse(page=page, page_size=page_size, total=total,
        total_pages=max(1, (total + page_size - 1) // page_size)))


@router.get("/{report_id}", response_model=ApiResponse[dict], summary="Get report job progress")
async def report_progress(report_id: UUID, user: AuthUser = Depends(get_current_user),
                          svc: ReportService = Depends(_get_service)):
    return ApiResponse(data=await svc.get(str(report_id), user.enterprise_id))


@router.post("/{report_id}/retry", response_model=ApiResponse[dict], status_code=202, summary="Retry a failed report")
async def retry_report(report_id: UUID, user: AuthUser = Depends(require_roles(*_REPORT_ROLES)),
                       svc: ReportService = Depends(_get_service)):
    return ApiResponse(data=await svc.retry(str(report_id), user.enterprise_id, user.user_id))


@router.get("/{report_id}/download", response_model=ApiResponse[dict], summary="Pre-signed download URL")
async def download_report(
    report_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report download requires enterprise-wide scope")
    return ApiResponse(data=await svc.download_url(report_id, user.enterprise_id))
