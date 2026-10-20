"""One isolated, time-bounded report attempt. Invoked by the durable worker."""
import asyncio
import io
import json
import os
import signal
import sys
import threading
from uuid import uuid4

from minio import Minio
from sqlalchemy import func, select
import urllib3

from src.core.exceptions import VisionGuardException
from src.core.settings import settings
from src.modules.identity.infrastructure.repositories import UserRepository
from src.modules.reports.application.jobs import JOB_TIMEOUT_SECONDS, set_progress
from src.modules.reports.application.services import ReportService
from src.modules.reports.infrastructure.generators import build_pdf, build_xlsx
from src.shared.database.models import Enterprise, Report, User
from src.shared.database.session import AsyncSessionFactory, engine


async def authorized(requester_id, enterprise_id):
    async with AsyncSessionFactory() as db:
        public_id = await db.scalar(select(User.public_id).join(Enterprise, Enterprise.id == User.enterprise_id).where(
            User.id == requester_id, User.enterprise_id == enterprise_id, Enterprise.status == "Active",
            Enterprise.is_active.is_(True), Enterprise.deleted_at.is_(None)))
        if not public_id:
            return False
        user = await UserRepository(db).get_by_id(public_id)
        return bool(user and user.is_active and set(user.roles) & {"SYSTEM_ADMIN", "ENTERPRISE_ADMIN"})


def storage_client():
    return Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY, secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE, region="us-east-1", http_client=urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=3, read=15), retries=urllib3.Retry(total=1, backoff_factor=0.2)))


async def execute_report(report_id, token):
    async with AsyncSessionFactory() as db:
        result = (await db.execute(select(Report, Enterprise.public_id, Enterprise.name).join(
            Enterprise, Enterprise.id == Report.enterprise_id).where(Report.public_id == report_id,
                Report.lease_token == token, Report.status == "Running",
                Report.lease_expires_at > func.clock_timestamp()))).one_or_none()
        if result is None:
            return 0  # Superseded attempt cannot publish a result.
        row, enterprise_public_id, enterprise_name = result
        if not await authorized(row.generated_by, row.enterprise_id):
            return 11
        limit = 5000 if row.format == "pdf" else 50000
        service = ReportService(db)
        try:
            if row.report_type == "violations_summary":
                title = "PPE Violations Report"
                headers, rows = await service._violation_rows(row.enterprise_id, row.from_date, row.to_date, limit)
            else:
                title = "Alerts Report"
                headers, rows = await service._alert_rows(row.enterprise_id, row.from_date, row.to_date, limit)
        except VisionGuardException as error:
            if error.code == "REPORT_TOO_LARGE":
                return 10
            raise
    if not await set_progress(report_id, token, stage="Rendering", row_count=len(rows)):
        return 0
    try:
        period = f"{row.from_date.isoformat()} to {row.to_date.isoformat()}"
        build = build_pdf if row.format == "pdf" else build_xlsx
        content = build(title, enterprise_name, period, headers, rows)
    except Exception:
        return 12
    if not await set_progress(report_id, token, stage="Uploading"):
        return 0
    # Each attempt has a private key. A stale child cannot overwrite a newer
    # result even if its upload finishes after its lease expires.
    key = f"{enterprise_public_id}/reports/{report_id}/{uuid4()}.{row.format}"
    client = storage_client()
    uploaded = completed = False
    try:
        try:
            client.put_object(settings.MINIO_BUCKET_REPORTS, key, io.BytesIO(content), len(content),
                content_type="application/pdf" if row.format == "pdf" else
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            uploaded = True
        except Exception:
            return 13
        if not await authorized(row.generated_by, row.enterprise_id):
            return 11
        # A lost commit response is ambiguous: preserve the object rather than
        # deleting a file that a successfully committed report may reference.
        completed = None
        completed = await set_progress(report_id, token, status="Completed", stage="Completed",
            object_key=key, completed_at=func.clock_timestamp(), failure_code=None, lease_token=None, lease_expires_at=None)
        return 0
    finally:
        if uploaded and completed is False:
            try:
                client.remove_object(settings.MINIO_BUCKET_REPORTS, key)
            except Exception:
                pass  # Unreferenced attempt object; never exposed through the API.


def main():
    # The child retains its own deadline even if its parent process crashes.
    timer = threading.Timer(JOB_TIMEOUT_SECONDS, lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(JOB_TIMEOUT_SECONDS)
    async def run():
        try:
            request = json.loads(sys.stdin.buffer.read(4096))
            return await execute_report(request["report_id"], request["token"])
        finally:
            await engine.dispose()
    try:
        result = asyncio.run(run())
    except Exception:
        result = 1
    finally:
        timer.cancel()
    raise SystemExit(result)


if __name__ == "__main__":
    main()
