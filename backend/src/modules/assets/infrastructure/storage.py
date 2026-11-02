"""Private reference/evidence objects, always served through the API."""
import asyncio
import io

from minio import Minio
import urllib3

from src.core.exceptions import VisionGuardException
from src.core.settings import settings

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _client():
    return Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY, secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE, region="us-east-1", http_client=urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=2, read=10), retries=urllib3.Retry(total=0)))


async def store_image(key, content):
    try:
        await asyncio.wait_for(asyncio.to_thread(_client().put_object, settings.MINIO_BUCKET_SNAPSHOTS,
            key, io.BytesIO(content), len(content), content_type="image/jpeg"), timeout=20)
    except Exception:
        raise VisionGuardException("EVIDENCE_STORAGE_UNAVAILABLE", "Image storage is unavailable; retry shortly", 503)


async def read_image(key):
    def read():
        response = _client().get_object(settings.MINIO_BUCKET_SNAPSHOTS, key)
        try:
            return response.read(MAX_IMAGE_BYTES + 1)
        finally:
            response.close()
            response.release_conn()
    try:
        content = await asyncio.wait_for(asyncio.to_thread(read), timeout=20)
    except Exception:
        raise VisionGuardException("EVIDENCE_STORAGE_UNAVAILABLE", "Image is unavailable; retry later", 503)
    if len(content) > MAX_IMAGE_BYTES:
        raise VisionGuardException("EVIDENCE_INTEGRITY_FAILED", "Stored image failed validation", 409)
    return content
