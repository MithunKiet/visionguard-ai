"""Durable report claims; every progress/result write is fenced by the attempt."""
import asyncio
from datetime import timedelta
import json
import sys
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
import structlog

from src.shared.database.models import Report
from src.shared.database.session import AsyncSessionFactory

log = structlog.get_logger()
JOB_TIMEOUT_SECONDS = 120
LEASE_SECONDS = 150
ACTIVE_STATUSES = ("Queued", "Running", "Retrying")
FAILURES = {
    "REPORT_TOO_LARGE": "Too many rows. Choose a shorter period or use Excel for up to 50,000 rows.",
    "REQUESTER_UNAUTHORIZED": "The requesting account no longer has enterprise report access. Create a new request with an authorized account.",
    "GENERATION_FAILED": "The report could not be rendered. Retry or contact an administrator.",
    "STORAGE_UNAVAILABLE": "Report storage is unavailable. Check storage connectivity and retry.",
    "ATTEMPT_TIMEOUT": "Generation exceeded the two-minute attempt limit. Choose a shorter period or retry.",
    "WORKER_INTERRUPTED": "The report worker was interrupted. Retry the report.",
}


async def claim_report(report_id=None):
    async with AsyncSessionFactory() as db, db.begin():
        due = or_(and_(Report.status.in_(["Queued", "Retrying"]), Report.next_attempt_at <= func.now()),
                  and_(Report.status == "Running", Report.lease_expires_at <= func.now()))
        query = select(Report).where(due, Report.deleted_at.is_(None)).order_by(
            Report.next_attempt_at, Report.id).limit(1).with_for_update(skip_locked=True)
        if report_id:
            query = query.where(Report.public_id == report_id)
        row = await db.scalar(query)
        if row is None:
            return None
        if row.attempts >= row.attempt_limit:
            row.status = row.stage = "Failed"
            row.failure_code = "WORKER_INTERRUPTED"
            row.lease_token = row.lease_expires_at = None
            return None
        now = await db.scalar(select(func.clock_timestamp()))
        row.attempts += 1
        row.status = "Running"
        row.stage = "Reading"
        row.failure_code = None
        row.row_count = None
        row.started_at = now
        row.lease_token = str(uuid4())
        row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        return row.public_id, row.lease_token


async def set_progress(report_id, token, **values):
    async with AsyncSessionFactory() as db, db.begin():
        result = await db.execute(update(Report).where(Report.public_id == report_id, Report.lease_token == token,
            Report.status == "Running", Report.lease_expires_at > func.clock_timestamp()).values(**values))
        return result.rowcount == 1


async def fail_attempt(report_id, token, code):
    async with AsyncSessionFactory() as db, db.begin():
        row = await db.scalar(select(Report).where(Report.public_id == report_id,
            Report.lease_token == token, Report.status == "Running").with_for_update())
        if row is None:
            return
        terminal = code in {"REPORT_TOO_LARGE", "REQUESTER_UNAUTHORIZED", "GENERATION_FAILED"}
        row.status = row.stage = "Failed" if terminal or row.attempts >= row.attempt_limit else "Retrying"
        row.failure_code = code
        row.lease_token = row.lease_expires_at = None
        row.next_attempt_at = await db.scalar(select(func.clock_timestamp())) + timedelta(seconds=min(300, 30 * 2 ** min(row.attempts - 1, 4)))


async def run_child(report_id, token):
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "src.modules.reports.runner",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(process.communicate(json.dumps({"report_id": report_id, "token": token}).encode()),
                               timeout=JOB_TIMEOUT_SECONDS)
        return process.returncode
    except TimeoutError:
        return 124
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


class ReportWorker:
    def __init__(self):
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def run(self):
        while True:
            try:
                if await self.process_one():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.error("reports.worker_failed", error_type=type(error).__name__)
            await asyncio.sleep(2)

    async def process_one(self, report_id=None):
        claim = await claim_report(report_id)
        if claim is None:
            return False
        try:
            result = await run_child(*claim)
            if result == 0:
                # A successful child must have committed Completed itself.
                # If it died before that write, this also recovers the job.
                await fail_attempt(*claim, "WORKER_INTERRUPTED")
            else:
                code = {10: "REPORT_TOO_LARGE", 11: "REQUESTER_UNAUTHORIZED", 12: "GENERATION_FAILED",
                        13: "STORAGE_UNAVAILABLE", 124: "ATTEMPT_TIMEOUT"}.get(result, "WORKER_INTERRUPTED")
                await fail_attempt(*claim, code)
        except asyncio.CancelledError:
            # The child is reaped by run_child. A process crash instead leaves
            # a finite lease, reclaimable by another API replica.
            await fail_attempt(*claim, "WORKER_INTERRUPTED")
            raise
        except Exception:
            await fail_attempt(*claim, "WORKER_INTERRUPTED")
        return True


report_worker = ReportWorker()
