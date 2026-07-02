import structlog
from minio import Minio
from src.core.settings import settings

log = structlog.get_logger()

_minio: Minio | None = None
_minio_public: Minio | None = None

# Fixed region avoids minio-py's auto-detection HTTP call (BucketLocation
# lookup), which would otherwise require the public-facing client to
# actually reach MINIO_PUBLIC_ENDPOINT — often not routable from inside a
# Docker container. MinIO's default single-node setup has no real region
# concept; any fixed value that matches on both clients works.
_REGION = "us-east-1"

BUCKETS = [
    settings.MINIO_BUCKET_SNAPSHOTS,
    settings.MINIO_BUCKET_LOGOS,
    settings.MINIO_BUCKET_REPORTS,
    settings.MINIO_BUCKET_MODELS,
]


async def init_minio() -> None:
    global _minio, _minio_public
    _minio = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
        region=_REGION,
    )
    for bucket in BUCKETS:
        if not _minio.bucket_exists(bucket):
            _minio.make_bucket(bucket)
            log.info("minio.bucket_created", bucket=bucket)

    # Separate client pointed at the publicly reachable endpoint, used only
    # to sign presigned URLs so the browser can actually resolve the host.
    # With region fixed above, signing needs no network call, so this client
    # never needs to actually connect to MINIO_PUBLIC_ENDPOINT itself.
    if settings.MINIO_PUBLIC_ENDPOINT == settings.MINIO_ENDPOINT:
        _minio_public = _minio
    else:
        _minio_public = Minio(
            settings.MINIO_PUBLIC_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
            region=_REGION,
        )


def get_minio() -> Minio:
    if _minio is None:
        raise RuntimeError("MinIO not initialized")
    return _minio


def get_presigned_url(bucket: str, object_key: str, expires_hours: int = 24) -> str:
    from datetime import timedelta
    if _minio_public is None:
        raise RuntimeError("MinIO not initialized")
    return _minio_public.presigned_get_object(bucket, object_key, expires=timedelta(hours=expires_hours))
