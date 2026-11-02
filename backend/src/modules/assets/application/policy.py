"""Monitored-asset entries carried inside the versioned zone policy.

The push payload carries the whole zone; the worker HTTP assignment carries
one camera's slice. Both use the same entry shape and ordering so a worker
can compare them without re-applying an unchanged policy.
"""
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import aggregate_order_by

from src.shared.database.models import Camera, SafetyAsset


def _monitored_conditions():
    return (SafetyAsset.monitoring_enabled.is_(True), SafetyAsset.is_active.is_(True),
            SafetyAsset.deleted_at.is_(None), SafetyAsset.roi_fingerprint.is_not(None),
            SafetyAsset.scene_fingerprint.is_not(None), SafetyAsset.roi_x.is_not(None))


def policy_entry(asset, camera_public_id):
    return {
        "asset_id": asset.public_id,
        "asset_code": asset.asset_code,
        "camera_id": camera_public_id,
        "roi": [asset.roi_x, asset.roi_y, asset.roi_width, asset.roi_height],
        "roi_fingerprint": asset.roi_fingerprint,
        "scene_fingerprint": asset.scene_fingerprint,
        "check_interval_seconds": asset.check_interval_seconds,
        "change_after_seconds": asset.change_after_seconds,
        "similarity_threshold": asset.similarity_threshold,
        "reference_sha256": asset.reference_sha256,
        "version": asset.version,
    }


async def zone_asset_policy(db, zone_pk: int) -> list[dict]:
    rows = (await db.execute(select(SafetyAsset, Camera.public_id)
        .join(Camera, Camera.id == SafetyAsset.camera_id)
        .where(SafetyAsset.zone_id == zone_pk, Camera.deleted_at.is_(None), *_monitored_conditions())
        .order_by(SafetyAsset.public_id))).all()
    return [policy_entry(asset, camera_id) for asset, camera_id in rows]


def camera_assets_column():
    """Correlated JSON column for the worker assignment query, so the
    assignment payload stays one statement regardless of camera count.
    Must build the same entries as policy_entry()."""
    entry = func.jsonb_build_object(
        "asset_id", SafetyAsset.public_id, "asset_code", SafetyAsset.asset_code, "camera_id", Camera.public_id,
        "roi", func.jsonb_build_array(SafetyAsset.roi_x, SafetyAsset.roi_y, SafetyAsset.roi_width, SafetyAsset.roi_height),
        "roi_fingerprint", SafetyAsset.roi_fingerprint, "scene_fingerprint", SafetyAsset.scene_fingerprint,
        "check_interval_seconds", SafetyAsset.check_interval_seconds,
        "change_after_seconds", SafetyAsset.change_after_seconds,
        "similarity_threshold", SafetyAsset.similarity_threshold,
        "reference_sha256", SafetyAsset.reference_sha256, "version", SafetyAsset.version)
    return (select(func.coalesce(func.jsonb_agg(aggregate_order_by(entry, SafetyAsset.public_id)), text("'[]'::jsonb")))
        .where(SafetyAsset.camera_id == Camera.id, *_monitored_conditions())
        .correlate(Camera).scalar_subquery().label("monitored_assets"))
