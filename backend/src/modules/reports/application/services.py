"""
ReportService — generate violation/alert summary reports as PDF or Excel,
store them in the MinIO reports bucket, and serve pre-signed download URLs
(master context rule #10: never expose direct MinIO URLs).
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.core.settings import settings
from src.modules.reports.infrastructure.generators import build_pdf, build_xlsx
from src.shared.database.models import Alert, Camera, Enterprise, PPEViolation, Report, User, Zone
from src.shared.database.pid import to_pk, to_public_id
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
        enterprise_id: str,
        generated_by: str,
        report_type: str,
        fmt: str,
        from_date: datetime,
        to_date: datetime,
    ) -> dict:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        enterprise = (await self._db.execute(
            select(Enterprise).where(Enterprise.id == ent_pk)
        )).scalar_one_or_none()
        enterprise_name = enterprise.name if enterprise else "VisionGuard AI"
        enterprise_code = enterprise.code if enterprise else "VG"

        if report_type == "violations_summary":
            title = "PPE Violations Report"
            headers, rows = await self._violation_rows(ent_pk, from_date, to_date)
        else:
            title = "Alerts Report"
            headers, rows = await self._alert_rows(ent_pk, from_date, to_date)

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
            enterprise_id=ent_pk,
            report_type=report_type,
            format=fmt,
            from_date=from_date,
            to_date=to_date,
            object_key=object_key,
            status="Completed",
            generated_by=await to_pk(self._db, User, generated_by),
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("report.generated", report_id=str(row.public_id), type=report_type, format=fmt)
        return await self.to_dict(self._db, row)

    async def list(self, enterprise_id: str, limit: int = 50) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        rows = (await self._db.execute(
            select(Report)
            .where(Report.enterprise_id == ent_pk)
            .order_by(Report.created_at.desc())
            .limit(limit)
        )).scalars()
        return [await self.to_dict(self._db, r) for r in rows]

    async def download_url(self, report_id: str, enterprise_id: str) -> dict:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        row = (await self._db.execute(
            select(Report).where(Report.public_id == report_id, Report.enterprise_id == ent_pk)
        )).scalar_one_or_none()
        if not row or not row.object_key:
            raise NotFoundException("Report", str(report_id))
        return {
            "report_id": report_id,
            "download_url": get_presigned_url(settings.MINIO_BUCKET_REPORTS, row.object_key, expires_hours=1),
        }

    # ── Data extraction ─────────────────────────────────────────────────────

    async def _violation_rows(
        self, ent_pk: int, from_date: datetime, to_date: datetime
    ) -> tuple[list[str], list[list]]:
        q = (
            select(PPEViolation, Zone.name, Camera.code)
            .join(Zone, Zone.id == PPEViolation.zone_id)
            .join(Camera, Camera.id == PPEViolation.camera_id)
            .where(
                PPEViolation.enterprise_id == ent_pk,
                PPEViolation.created_at >= from_date,
                PPEViolation.created_at <= to_date,
            )
            .order_by(PPEViolation.created_at.desc())
            .limit(5000)
        )
        rows = (await self._db.execute(q)).all()
        headers = ["Date/Time (UTC)", "Zone", "Camera", "Violation", "Confidence", "False Positive"]
        return headers, [
            [
                v.created_at.strftime("%Y-%m-%d %H:%M"),
                zone_name,
                camera_code,
                v.violation_type.replace("_", " ").title(),
                f"{v.confidence:.2f}",
                "Yes" if v.is_false_positive else "No",
            ]
            for v, zone_name, camera_code in rows
        ]

    async def _alert_rows(
        self, ent_pk: int, from_date: datetime, to_date: datetime
    ) -> tuple[list[str], list[list]]:
        q = (
            select(Alert, Zone.name)
            .join(Zone, Zone.id == Alert.zone_id)
            .where(
                Alert.enterprise_id == ent_pk,
                Alert.created_at >= from_date,
                Alert.created_at <= to_date,
            )
            .order_by(Alert.created_at.desc())
            .limit(5000)
        )
        rows = (await self._db.execute(q)).all()
        headers = ["Alert #", "Date/Time (UTC)", "Zone", "Type", "Severity", "Status", "Resolved At"]
        return headers, [
            [
                a.alert_number,
                a.created_at.strftime("%Y-%m-%d %H:%M"),
                zone_name,
                a.alert_type,
                a.severity,
                a.status,
                a.resolved_on.strftime("%Y-%m-%d %H:%M") if a.resolved_on else "—",
            ]
            for a, zone_name in rows
        ]

    @staticmethod
    async def to_dict(db: AsyncSession, r: Report) -> dict:
        return {
            "id": r.public_id,
            "report_type": r.report_type,
            "format": r.format,
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "status": r.status,
            "generated_by": await to_public_id(db, User, r.generated_by),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
