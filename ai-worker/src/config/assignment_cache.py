"""Time-limited offline assignments; authorization rejection always clears cache."""
import asyncio
import hashlib
from uuid import UUID

import httpx
import structlog

from src.config.settings import settings
from src.health.metrics import edge_cache_active

log = structlog.get_logger()


def authorization_identity():
    return hashlib.sha256(f"{settings.BACKEND_API_URL}\0{settings.WORKER_API_KEY}".encode()).hexdigest()


def validate_assignments(cameras):
    if not isinstance(cameras, list):
        raise ValueError("Invalid assignment response")
    seen = set()
    for camera in cameras:
        if not isinstance(camera, dict) or camera.get("enterprise_id") != settings.ENTERPRISE_ID:
            raise ValueError("Assignment enterprise mismatch")
        for key in ("camera_id", "factory_id", "zone_id", "enterprise_id"):
            if not isinstance(camera.get(key), str):
                raise ValueError("Invalid assignment identifier")
            UUID(camera[key])
        if camera["camera_id"] in seen:
            raise ValueError("Duplicate assignment")
        seen.add(camera["camera_id"])
        if not isinstance(camera.get("rtsp_url"), str) or not camera["rtsp_url"].startswith(("rtsp://", "rtsps://")):
            raise ValueError("Invalid assignment stream")
        for key in ("zone_config", "ppe_overrides"):
            if camera.get(key) is not None and not isinstance(camera[key], dict):
                raise ValueError("Invalid assignment configuration")
    return cameras


async def refresh_assignments(journal, register, fetch):
    revision = await asyncio.to_thread(journal.cache_revision)
    try:
        await register()
        cameras = validate_assignments(await fetch())
    except (httpx.TransportError, httpx.HTTPStatusError) as error:
        retryable = isinstance(error, httpx.TransportError) or error.response.status_code >= 500 or error.response.status_code == 429
        if not retryable:
            await asyncio.to_thread(journal.clear_cache)
            edge_cache_active.set(0)
            log.error("assignments.access_rejected")
            return []
        cached = await asyncio.to_thread(journal.load_cache, settings.EDGE_ASSIGNMENT_CACHE_SECONDS, authorization_identity())
        edge_cache_active.set(bool(cached))
        log.warning("assignments.backend_unavailable", cached_cameras=len(cached))
        return validate_assignments(cached)
    except (ValueError, TypeError, KeyError):
        await asyncio.to_thread(journal.clear_cache)
        edge_cache_active.set(0)
        log.error("assignments.invalid_response")
        return []
    saved = await asyncio.to_thread(journal.save_cache, cameras, authorization_identity(), revision)
    edge_cache_active.set(0)
    return cameras if saved else []
