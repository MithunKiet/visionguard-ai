"""
ReportService — generate violation/alert summary reports as PDF or Excel,
store them in the MinIO reports bucket, and serve pre-signed download URLs
(master context rule #10: never expose direct MinIO URLs).
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.core.settings import settings
from src.modules.reports.infrastructure.generators import build_pdf, build_xlsx
from src.shared.database.models import Alert, Camera, Enterprise, PPEViolation, Report, Zone
from src.shared.storage.minio_client import get_minio, get_presigned_url

log = structlog.get_logger()

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ReportService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def generate(
        self,
        enterprise_id: UUID,
        generated_by: UUID,
        report_type: str,
        fmt: str,
        from_date: datetime,
        to_date: datetime,
    ) -> dict:
        enterprise = (await self._db.execute(
            select(Enterprise).where(Enterprise.id == enterprise_id)
        )).scalar_one_or_none()
        enterprise_name = enterprise.name if enterprise else "VisionGuard AI"
        enterprise_code = enterprise.code if enterprise else "VG"

        if report_type == "violations_summary":
            title = "PPE Violations Report"
            headers, rows = await self._violation_rows(enterprise_id, from_date, to_date)
        else:
            title = "Alerts Report"
            headers, rows = await self._alert_rows(enterprise_id, from_date, to_date)

        period = f"{from_date.date().isoformat()} to {to_date.date().isoformat()}"
        if fmt == "pdf":
            content = build_pdf(title, enterprise_name, period, headers, rows)
        else:
            content = build_xlsx(title, enterprise_name, period, headers, rows)

        report_id = uuid.uuid4()
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        object_key = f"{enterprise_id}/{month}/{enterprise_code}_{report_type}_{report_id}.{fmt}"

        get_minio().put_object(
            settings.MINIO_BUCKET_REPORTS,
            object_key,
            data=io.BytesIO(content),
            length=len(content),
            content_type=_CONTENT_TYPES[fmt],
        )

        row = Report(
            id=report_id,
            enterprise_id=enterprise_id,
            report_type=report_type,
            format=fmt,
            from_date=from_date,
            to_date=to_date,
            object_key=object_key,
            status="Completed",
            generated_by=generated_by,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("report.generated", report_id=str(report_id), type=report_type, format=fmt)
        return self.to_dict(row)

    async def list(self, enterprise_id: UUID, limit: int = 50) -> list[dict]:
        rows = (await self._db.execute(
            select(Report)
            .where(Report.enterprise_id == enterprise_id)
            .order_by(Report.created_on.desc())
            .limit(limit)
        )).scalars()
        return [self.to_dict(r) for r in rows]

    async def download_url(self, report_id: UUID, enterprise_id: UUID) -> dict:
        row = (await self._db.execute(
            select(Report).where(Report.id == report_id, Report.enterprise_id == enterprise_id)
        )).scalar_one_or_none()
        if not row or not row.object_key:
            raise NotFoundException("Report", str(report_id))
        return {
            "report_id": str(report_id),
            "download_url": get_presigned_url(settings.MINIO_BUCKET_REPORTS, row.object_key, expires_hours=1),
        }

    # ── Data extraction ─────────────────────────────────────────────────────

    async def _violation_rows(
        self, enterprise_id: UUID, from_date: datetime, to_date: datetime
    ) -> tuple[list[str], list[list]]:
        q = (
            select(PPEViolation, Zone.name, Camera.code)
            .join(Zone, Zone.id == PPEViolation.zone_id)
            .join(Camera, Camera.id == PPEViolation.camera_id)
            .where(
                PPEViolation.enterprise_id == enterprise_id,
                PPEViolation.created_on >= from_date,
                PPEViolation.created_on <= to_date,
            )
            .order_by(PPEViolation.created_on.desc())
            .limit(5000)
        )
        rows = (await self._db.execute(q)).all()
        headers = ["Date/Time (UTC)", "Zone", "Camera", "Violation", "Confidence", "False Positive"]
        return headers, [
            [
                v.created_on.strftime("%Y-%m-%d %H:%M"),
                zone_name,
                camera_code,
                v.violation_type.replace("_", " ").title(),
                f"{v.confidence:.2f}",
                "Yes" if v.is_false_positive else "No",
            ]
            for v, zone_name, camera_code in rows
        ]

    async def _alert_rows(
        self, enterprise_id: UUID, from_date: datetime, to_date: datetime
    ) -> tuple[list[str], list[list]]:
        q = (
            select(Alert, Zone.name)
            .join(Zone, Zone.id == Alert.zone_id)
            .where(
                Alert.enterprise_id == enterprise_id,
                Alert.created_on >= from_date,
                Alert.created_on <= to_date,
            )
            .order_by(Alert.created_on.desc())
            .limit(5000)
        )
        rows = (await self._db.execute(q)).all()
        headers = ["Alert #", "Date/Time (UTC)", "Zone", "Type", "Severity", "Status", "Resolved At"]
        return headers, [
            [
                a.alert_number,
                a.created_on.strftime("%Y-%m-%d %H:%M"),
                zone_name,
                a.alert_type,
                a.severity,
                a.status,
                a.resolved_on.strftime("%Y-%m-%d %H:%M") if a.resolved_on else "—",
            ]
            for a, zone_name in rows
        ]

    @staticmethod
    def to_dict(r: Report) -> dict:
        return {
            "id": str(r.id),
            "report_type": r.report_type,
            "format": r.format,
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "status": r.status,
            "generated_by": str(r.generated_by) if r.generated_by else None,
            "created_on": r.created_on.isoformat() if r.created_on else None,
        }
