import structlog
from minio import Minio
from src.core.settings import settings

log = structlog.get_logger()

_minio: Minio | None = None

BUCKETS = [
    settings.MINIO_BUCKET_SNAPSHOTS,
    settings.MINIO_BUCKET_LOGOS,
    settings.MINIO_BUCKET_REPORTS,
    settings.MINIO_BUCKET_MODELS,
]


async def init_minio() -> None:
    global _minio
    _minio = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )
    for bucket in BUCKETS:
        if not _minio.bucket_exists(bucket):
            _minio.make_bucket(bucket)
            log.info("minio.bucket_created", bucket=bucket)


def get_minio() -> Minio:
    if _minio is None:
        raise RuntimeError("MinIO not initialized")
    return _minio


def get_presigned_url(bucket: str, object_key: str, expires_hours: int = 24) -> str:
    from datetime import timedelta
    return get_minio().presigned_get_object(bucket, object_key, expires=timedelta(hours=expires_hours))
