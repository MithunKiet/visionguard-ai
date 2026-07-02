from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reports.api.schemas import GenerateReportRequest
from src.modules.reports.application.services import ReportService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles

router = APIRouter(prefix="/reports", tags=["Reports"])

_REPORT_ROLES = ("SUPER_ADMIN", "HO_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER")


def _get_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    return ReportService(db)


@router.post("/generate", response_model=ApiResponse[dict], summary="Generate a PDF/Excel report")
async def generate_report(
    body: GenerateReportRequest,
    user: AuthUser = Depends(require_roles(*_REPORT_ROLES)),
    svc: ReportService = Depends(_get_service),
):
    return ApiResponse(data=await svc.generate(
        UUID(user.enterprise_id), UUID(user.user_id),
        body.report_type, body.format, body.from_date, body.to_date,
    ))


@router.get("", response_model=ApiResponse[list], summary="List generated reports")
async def list_reports(
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    return ApiResponse(data=await svc.list(UUID(user.enterprise_id)))


@router.get("/{report_id}/download", response_model=ApiResponse[dict], summary="Pre-signed download URL")
async def download_report(
    report_id: UUID,
    user: AuthUser = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
):
    return ApiResponse(data=await svc.download_url(report_id, UUID(user.enterprise_id)))
