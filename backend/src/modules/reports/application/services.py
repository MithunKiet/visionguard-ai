"""
ReportService — queue durable PDF/Excel jobs and serve scoped progress/downloads
(master context rule #10: never expose direct MinIO URLs).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, VisionGuardException
from src.core.settings import settings
from src.modules.reports.application.jobs import ACTIVE_STATUSES, FAILURES
from src.shared.database.models import Alert, Camera, Enterprise, PPEViolation, Report, User, Zone
from src.shared.database.pid import to_pk
from src.shared.storage.minio_client import get_presigned_url


class ReportService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def generate(self, enterprise_id, generated_by, report_type, fmt, from_date, to_date, request_key=None):
        # Serialize admission and duplicate keys within an enterprise. No file
        # generation, broker or storage operation is performed in this request.
        enterprise = await self._db.scalar(select(Enterprise).where(
            Enterprise.public_id == enterprise_id).with_for_update())
        if enterprise is None:
            raise NotFoundException("Enterprise", enterprise_id)
        user_pk = await to_pk(self._db, User, generated_by)
        if request_key:
            existing = await self._db.scalar(select(Report).where(
                Report.enterprise_id == enterprise.id, Report.request_key == request_key))
            if existing:
                if (existing.generated_by != user_pk or existing.report_type != report_type or existing.format != fmt
                        or existing.from_date != from_date or existing.to_date != to_date):
                    raise VisionGuardException("REPORT_KEY_CONFLICT", "This request key was used for another report", 409)
                return self.to_dict(existing, generated_by)
        await self._check_capacity(enterprise.id)
        row = Report(enterprise_id=enterprise.id, generated_by=user_pk, report_type=report_type, format=fmt,
            from_date=from_date, to_date=to_date, status="Queued", stage="Queued", request_key=request_key)
        self._db.add(row)
        await self._db.commit()
        return self.to_dict(row, generated_by)

    async def _check_capacity(self, enterprise_pk):
        count = await self._db.scalar(select(func.count()).select_from(Report).where(
            Report.enterprise_id == enterprise_pk, Report.status.in_(ACTIVE_STATUSES), Report.deleted_at.is_(None)))
        if count >= 10:
            raise VisionGuardException("REPORT_QUEUE_FULL", "Ten reports are already active. Wait for one to finish.", 429)

    async def list(self, enterprise_id, page=1, page_size=20):
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        filters = (Report.enterprise_id == ent_pk, Report.deleted_at.is_(None))
        total = await self._db.scalar(select(func.count()).select_from(Report).where(*filters))
        rows = (await self._db.execute(select(Report, User.public_id).outerjoin(User, User.id == Report.generated_by)
            .where(*filters).order_by(Report.created_at.desc(), Report.id.desc())
            .offset((page - 1) * page_size).limit(page_size))).all()
        return [self.to_dict(row, user_id) for row, user_id in rows], total

    async def _row(self, report_id, enterprise_id, lock=False):
        query = select(Report, User.public_id).join(Enterprise, Enterprise.id == Report.enterprise_id).outerjoin(
            User, User.id == Report.generated_by).where(Report.public_id == report_id,
                Enterprise.public_id == enterprise_id, Report.deleted_at.is_(None))
        if lock:
            query = query.with_for_update(of=Report)
        result = (await self._db.execute(query)).one_or_none()
        if result is None:
            raise NotFoundException("Report", report_id)
        return result

    async def get(self, report_id, enterprise_id):
        row, user_id = await self._row(report_id, enterprise_id)
        return self.to_dict(row, user_id)

    async def retry(self, report_id, enterprise_id, actor):
        enterprise_pk = await self._db.scalar(select(Enterprise.id).where(
            Enterprise.public_id == enterprise_id).with_for_update())
        row, user_id = await self._row(report_id, enterprise_id, lock=True)
        if row.status in ACTIVE_STATUSES:
            return self.to_dict(row, user_id)  # Lost retry response cannot schedule duplicate work.
        if row.status != "Failed":
            raise VisionGuardException("REPORT_NOT_FAILED", "Only failed reports can be retried", 409)
        await self._check_capacity(enterprise_pk)
        row.status = row.stage = "Queued"
        row.attempt_limit = row.attempts + 3
        row.failure_code = None
        row.started_at = row.completed_at = None
        row.row_count = None
        row.next_attempt_at = func.clock_timestamp()
        row.updated_by = actor
        await self._db.commit()
        await self._db.refresh(row)
        return self.to_dict(row, user_id)

    async def download_url(self, report_id, enterprise_id):
        row, _ = await self._row(report_id, enterprise_id)
        if row.status != "Completed" or not row.object_key:
            raise VisionGuardException("REPORT_NOT_READY", "The report is not ready to download", 409)
        return {"report_id": report_id,
            "download_url": get_presigned_url(settings.MINIO_BUCKET_REPORTS, row.object_key, expires_hours=1)}

    # ── Data extraction ─────────────────────────────────────────────────────

    async def _violation_rows(
        self, ent_pk: int, from_date: datetime, to_date: datetime, limit: int = 5000
    ) -> tuple[list[str], list[list]]:
        q = (
            select(PPEViolation.created_at, PPEViolation.violation_type, PPEViolation.confidence,
                   PPEViolation.is_false_positive, Zone.name, Camera.code)
            .join(Zone, Zone.id == PPEViolation.zone_id)
            .join(Camera, Camera.id == PPEViolation.camera_id)
            .where(
                PPEViolation.enterprise_id == ent_pk, Zone.enterprise_id == ent_pk, Camera.enterprise_id == ent_pk,
                PPEViolation.created_at >= from_date,
                PPEViolation.created_at <= to_date,
            )
            .order_by(PPEViolation.created_at.desc(), PPEViolation.id.desc())
            .limit(limit + 1)
        )
        rows = (await self._db.execute(q)).all()
        if len(rows) > limit:
            raise VisionGuardException(code="REPORT_TOO_LARGE", message="Report exceeds its row limit; choose a shorter date range", status_code=422)
        headers = ["Date/Time (UTC)", "Zone", "Camera", "Violation", "Confidence", "False Positive"]
        return headers, [
            [
                created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                zone_name,
                camera_code,
                violation_type.replace("_", " ").title(),
                f"{confidence:.2f}",
                "Yes" if is_false_positive else "No",
            ]
            for created_at, violation_type, confidence, is_false_positive, zone_name, camera_code in rows
        ]

    async def _alert_rows(
        self, ent_pk: int, from_date: datetime, to_date: datetime, limit: int = 5000
    ) -> tuple[list[str], list[list]]:
        q = (
            select(Alert.alert_number, Alert.created_at, Alert.alert_type, Alert.severity,
                   Alert.status, Alert.resolved_on, Zone.name)
            .join(Zone, Zone.id == Alert.zone_id)
            .where(
                Alert.enterprise_id == ent_pk, Zone.enterprise_id == ent_pk,
                Alert.created_at >= from_date,
                Alert.created_at <= to_date,
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(limit + 1)
        )
        rows = (await self._db.execute(q)).all()
        if len(rows) > limit:
            raise VisionGuardException(code="REPORT_TOO_LARGE", message="Report exceeds its row limit; choose a shorter date range", status_code=422)
        headers = ["Alert #", "Date/Time (UTC)", "Zone", "Type", "Severity", "Status", "Resolved At"]
        return headers, [
            [
                alert_number,
                created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                zone_name,
                alert_type,
                severity,
                status,
                resolved_on.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if resolved_on else "—",
            ]
            for alert_number, created_at, alert_type, severity, status, resolved_on, zone_name in rows
        ]

    @staticmethod
    def to_dict(r: Report, generated_by: str | None) -> dict:
        return {
            "id": r.public_id,
            "report_type": r.report_type,
            "format": r.format,
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "status": r.status,
            "generated_by": generated_by,
            "stage": r.stage, "attempts": r.attempts, "row_count": r.row_count,
            "failure_code": r.failure_code, "failure_message": FAILURES.get(r.failure_code),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "next_attempt_at": r.next_attempt_at.isoformat() if r.status == "Retrying" else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
