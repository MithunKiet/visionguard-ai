from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reports.api.schemas import GenerateReportRequest
from src.modules.reports.application.services import ReportService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.core.exceptions import ForbiddenException
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.scope import get_scope

router = APIRouter(prefix="/reports", tags=["Reports"])

_REPORT_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    return ReportService(db)


@router.post("/generate", response_model=ApiResponse[dict], summary="Generate a PDF/Excel report")
async def generate_report(
    body: GenerateReportRequest,
    user: AuthUser = Depends(require_roles(*_REPORT_ROLES)),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report generation requires enterprise-wide scope")
    return ApiResponse(data=await svc.generate(
        user.enterprise_id, user.user_id,
        body.report_type, body.format, body.from_date, body.to_date,
    ))


@router.get("", response_model=ApiResponse[list], summary="List generated reports")
async def list_reports(
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report listing requires enterprise-wide scope")
    return ApiResponse(data=await svc.list(user.enterprise_id))


@router.get("/{report_id}/download", response_model=ApiResponse[dict], summary="Pre-signed download URL")
async def download_report(
    report_id: str,
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    if not get_scope(user).unrestricted:
        raise ForbiddenException("Report download requires enterprise-wide scope")
    return ApiResponse(data=await svc.download_url(report_id, user.enterprise_id))
