"""Report installed policies; every reconciliation retries lost confirmations."""
import asyncio

import httpx
import structlog

from src.config.ownership import SESSION_ID, lease_valid
from src.config.settings import settings

log = structlog.get_logger()


async def report_applications(workers):
    # Snapshot synchronously before network awaits. A concurrent hot update may
    # make this version stale; the backend rejects it and the next poll repairs it.
    applications = [{"camera_id": worker.camera_id, "zone_id": worker.zone_id, "lease_token": worker.lease["token"],
                     "version": worker.zone_config["version"], "detection_health": worker.detection_health()}
                    for worker in workers if lease_valid(worker.lease)]
    if not applications:
        return
    try:
        async with asyncio.timeout(10), httpx.AsyncClient(timeout=5.0) as client:
            for offset in range(0, len(applications), 200):
                response = await client.post(
                    f"{settings.BACKEND_API_URL}/api/v1/workers/{settings.WORKER_ID}/config-applied",
                    headers={"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": settings.ENTERPRISE_ID,
                             "X-Worker-Session": SESSION_ID},
                    json={"applications": applications[offset:offset + 200]},
                )
                response.raise_for_status()
                if response.json()["data"]["rejected"]:
                    log.info("config_application.rejected", count=response.json()["data"]["rejected"])
    except Exception as error:
        # Never expose URLs, tokens or response bodies; HTTP failure must not
        # stop capture or acknowledge a policy that was never installed.
        log.warning("config_application.retry_on_reconcile", error_type=type(error).__name__)
