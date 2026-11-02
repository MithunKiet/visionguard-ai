"""Safety asset registry, reference capture and versioned monitoring policy."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import NotFoundException, VisionGuardException
from src.modules.assets.domain import fingerprint
from src.modules.assets.infrastructure.storage import read_image, store_image
from src.shared.database.models import (
    Alert, AssetIncident, Camera, Enterprise, Factory, SafetyAsset, Zone,
)
from src.shared.security.resource_policy import scoped_query

MANAGE_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")
# Fields that change what the worker evaluates and therefore version the zone policy.
_POLICY_FIELDS = ("roi", "check_interval_seconds", "change_after_seconds", "similarity_threshold", "monitoring_enabled")


def monitoring_status(asset, now=None):
    """Truthful state: a configured asset is unconfirmed until a worker reports it."""
    if not asset.monitoring_enabled:
        return "Disabled"
    if asset.roi_fingerprint is None or asset.scene_fingerprint is None:
        return "NotConfigured"
    now = now or datetime.now(timezone.utc)
    stale_after = timedelta(seconds=max(3 * asset.check_interval_seconds, 180))
    if asset.last_checked_at is None or now - asset.last_checked_at > stale_after or asset.last_state is None:
        return "Unconfirmed"
    return asset.last_state


def decode_jpeg(content):
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise VisionGuardException("INVALID_REFERENCE", "The camera returned an unreadable frame", 422)
    return image


class AssetService:
    def __init__(self, db, user):
        self.db, self.user = db, user

    async def _enterprise_pk(self):
        return await self.db.scalar(select(Enterprise.id).where(Enterprise.public_id == self.user.enterprise_id))

    async def _asset(self, asset_id, lock=False):
        query = select(SafetyAsset).where(SafetyAsset.public_id == str(asset_id),
            SafetyAsset.enterprise_id == await self._enterprise_pk(), SafetyAsset.deleted_at.is_(None))
        query = await scoped_query(self.db, query, SafetyAsset, user=self.user)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        asset = await self.db.scalar(query)
        if asset is None:
            raise NotFoundException("SafetyAsset", str(asset_id))
        return asset

    async def list(self, factory_id=None, zone_id=None, camera_id=None, page=1, page_size=50):
        ent_pk = await self._enterprise_pk()
        query = (select(SafetyAsset, Factory.public_id, Zone.public_id, Zone.name, Camera.public_id, Camera.name)
            .join(Factory, Factory.id == SafetyAsset.factory_id).join(Zone, Zone.id == SafetyAsset.zone_id)
            .join(Camera, Camera.id == SafetyAsset.camera_id)
            .where(SafetyAsset.enterprise_id == ent_pk, SafetyAsset.deleted_at.is_(None)))
        if factory_id:
            query = query.where(Factory.public_id == factory_id)
        if zone_id:
            query = query.where(Zone.public_id == zone_id)
        if camera_id:
            query = query.where(Camera.public_id == camera_id)
        query = await scoped_query(self.db, query, SafetyAsset, user=self.user)
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await self.db.execute(query.order_by(SafetyAsset.asset_code, SafetyAsset.id)
            .offset((page - 1) * page_size).limit(page_size))).all()
        now = datetime.now(timezone.utc)
        open_incidents = {}
        if rows:
            # One query for the page: the latest uncleared incident per asset.
            for incident in (await self.db.execute(select(AssetIncident)
                    .where(AssetIncident.asset_id.in_([asset.id for asset, *_ in rows]), AssetIncident.cleared_at.is_(None))
                    .order_by(AssetIncident.asset_id, AssetIncident.detected_at.desc())
                    .distinct(AssetIncident.asset_id))).scalars():
                open_incidents[incident.asset_id] = incident
        result = []
        for asset, *refs in rows:
            item = self._to_dict(asset, *refs, now=now)
            incident = open_incidents.get(asset.id)
            item["open_incident"] = incident_dict(incident, asset) if incident else None
            result.append(item)
        return result, total

    async def get(self, asset_id):
        asset = await self._asset(asset_id)
        return await self._detail(asset)

    async def create(self, body):
        camera = await self.db.scalar(select(Camera).where(Camera.public_id == body.camera_id,
            Camera.enterprise_id == await self._enterprise_pk(), Camera.deleted_at.is_(None)))
        if camera is None:
            raise NotFoundException("Camera", body.camera_id)
        asset = SafetyAsset(enterprise_id=camera.enterprise_id, factory_id=camera.factory_id, zone_id=camera.zone_id,
            camera_id=camera.id, asset_code=body.asset_code.strip(), name=body.name.strip(),
            location_desc=body.location_desc, asset_type=body.asset_type,
            check_interval_seconds=body.check_interval_seconds, change_after_seconds=body.change_after_seconds,
            similarity_threshold=body.similarity_threshold, monitoring_enabled=False,
            created_by=self.user.user_id, version=1)
        self.db.add(asset)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise VisionGuardException("ASSET_CODE_EXISTS", "Another asset already uses this code", 409)
        await self._audit("SAFETY_ASSET_CREATED", asset, None, self._audit_fields(asset))
        return await self._detail(asset)

    async def update(self, asset_id, body):
        asset = await self._asset(asset_id, lock=True)
        if body.version != asset.version:
            raise VisionGuardException("ASSET_CHANGED", "This asset changed since it was loaded; reload and retry", 409)
        old = self._audit_fields(asset)
        was_monitored = asset.monitoring_enabled
        changes = body.model_dump(exclude_unset=True, exclude={"version"})
        policy_changed = False
        if "roi" in changes:
            roi = changes.pop("roi")
            if roi is None:
                asset.roi_x = asset.roi_y = asset.roi_width = asset.roi_height = None
                asset.roi_fingerprint = None
            else:
                values = (roi["x"], roi["y"], roi["width"], roi["height"])
                try:
                    fingerprint.validate_roi(*values)
                except ValueError as error:
                    raise VisionGuardException("INVALID_ROI", str(error), 422)
                asset.roi_x, asset.roi_y, asset.roi_width, asset.roi_height = values
                asset.roi_fingerprint = None
                if asset.reference_key:
                    image = decode_jpeg(await self._verified_reference(asset))
                    asset.roi_fingerprint = fingerprint.encode(fingerprint.roi_fingerprint(image, self._roi(asset)))
            policy_changed = True
        for field in ("asset_type", "name", "location_desc", "check_interval_seconds", "change_after_seconds",
                      "similarity_threshold", "monitoring_enabled"):
            if field in changes and changes[field] is not None:
                if field in _POLICY_FIELDS and getattr(asset, field) != changes[field]:
                    policy_changed = True
                setattr(asset, field, changes[field].strip() if field == "name" else changes[field])
        if asset.monitoring_enabled and (asset.roi_fingerprint is None or asset.scene_fingerprint is None):
            raise VisionGuardException("ASSET_NOT_READY", "Capture a reference photo and mark the asset area before monitoring", 422)
        await self._save(asset, policy_changed and (was_monitored or asset.monitoring_enabled), "updated")
        await self._audit("SAFETY_ASSET_UPDATED", asset, old, self._audit_fields(asset))
        return await self._detail(asset)

    async def capture_reference(self, asset_id):
        from src.modules.camera.application.probe import capture_still
        asset = await self._asset(asset_id)
        asset_public_id = asset.public_id
        rtsp_url = await self.db.scalar(select(Camera.rtsp_url).where(Camera.id == asset.camera_id))
        # The camera read must not hold a transaction open for up to 12 seconds.
        await self.db.rollback()
        content = await capture_still(rtsp_url)
        if content is None:
            raise VisionGuardException("CAMERA_FRAME_UNAVAILABLE", "The camera did not return a frame; check its connection and retry", 503)
        image = await asyncio.to_thread(decode_jpeg, content)
        key = f"{self.user.enterprise_id}/assets/{asset_public_id}/reference/{uuid4()}.jpg"
        # Upload first; an unreferenced object is harmless, a row pointing at a
        # missing object is not. Never delete objects after an uncertain commit.
        await store_image(key, content)
        asset = await self._asset(asset_id, lock=True)
        old = self._audit_fields(asset)
        asset.reference_key = key
        asset.reference_sha256 = hashlib.sha256(content).hexdigest()
        asset.reference_height, asset.reference_width = image.shape[:2]
        asset.reference_captured_at = datetime.now(timezone.utc)
        asset.scene_fingerprint = fingerprint.encode(fingerprint.scene_fingerprint(image))
        asset.roi_fingerprint = (fingerprint.encode(fingerprint.roi_fingerprint(image, self._roi(asset)))
                                 if asset.roi_x is not None else None)
        await self._save(asset, asset.monitoring_enabled, "reference captured")
        await self._audit("SAFETY_ASSET_REFERENCE_CAPTURED", asset, old, self._audit_fields(asset))
        return await self._detail(asset)

    async def delete(self, asset_id):
        asset = await self._asset(asset_id, lock=True)
        old = self._audit_fields(asset)
        was_monitored = asset.monitoring_enabled
        asset.monitoring_enabled = False
        asset.is_active = False
        asset.deleted_at = datetime.now(timezone.utc)
        asset.deleted_by = self.user.user_id
        await self._save(asset, was_monitored, "deleted")
        await self._audit("SAFETY_ASSET_DELETED", asset, old, None)

    async def reference_image(self, asset_id):
        asset = await self._asset(asset_id)
        if not asset.reference_key:
            raise NotFoundException("SafetyAssetReference", str(asset_id))
        return await self._verified_reference(asset)

    async def incidents(self, asset_id, page=1, page_size=20):
        asset = await self._asset(asset_id)
        base = select(AssetIncident).where(AssetIncident.asset_id == asset.id)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        rows = (await self.db.execute(select(AssetIncident, Alert.public_id, Alert.alert_number, Alert.status)
            .outerjoin(Alert, Alert.id == AssetIncident.alert_id).where(AssetIncident.asset_id == asset.id)
            .order_by(AssetIncident.detected_at.desc(), AssetIncident.id.desc())
            .offset((page - 1) * page_size).limit(page_size))).all()
        return [incident_dict(incident, asset, alert_id, number, status)
                for incident, alert_id, number, status in rows], total

    async def incident_snapshot(self, asset_id, incident_id):
        asset = await self._asset(asset_id)
        key = await self.db.scalar(select(AssetIncident.snapshot_key).where(
            AssetIncident.public_id == str(incident_id), AssetIncident.asset_id == asset.id))
        if not key:
            raise NotFoundException("AssetIncidentSnapshot", str(incident_id))
        return await read_image(key)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _save(self, asset, publish, reason):
        asset.version += 1
        asset.updated_by = self.user.user_id
        if publish:
            from src.modules.config.application.services import ConfigService
            await self.db.flush()
            await ConfigService(self.db).bump_for_assets(asset.zone_id, self.user.enterprise_id, self.user.user_id,
                f"Safety asset {asset.asset_code} {reason}")
        await self.db.commit()

    async def _verified_reference(self, asset):
        content = await read_image(asset.reference_key)
        if hashlib.sha256(content).hexdigest() != asset.reference_sha256:
            raise VisionGuardException("EVIDENCE_INTEGRITY_FAILED", "Stored reference photo failed its integrity check", 409)
        return content

    @staticmethod
    def _roi(asset):
        return (asset.roi_x, asset.roi_y, asset.roi_width, asset.roi_height)

    async def _detail(self, asset):
        refs = (await self.db.execute(select(Factory.public_id, Zone.public_id, Zone.name, Camera.public_id, Camera.name)
            .select_from(SafetyAsset).join(Factory, Factory.id == SafetyAsset.factory_id)
            .join(Zone, Zone.id == SafetyAsset.zone_id).join(Camera, Camera.id == SafetyAsset.camera_id)
            .where(SafetyAsset.id == asset.id))).one()
        result = self._to_dict(asset, *refs)
        incident = (await self.db.execute(select(AssetIncident).where(AssetIncident.asset_id == asset.id,
            AssetIncident.cleared_at.is_(None)).order_by(AssetIncident.detected_at.desc()).limit(1))).scalar_one_or_none()
        result["open_incident"] = incident_dict(incident, asset) if incident else None
        return result

    @staticmethod
    def _to_dict(asset, factory_id, zone_id, zone_name, camera_id, camera_name, now=None):
        roi = None if asset.roi_x is None else {
            "x": asset.roi_x, "y": asset.roi_y, "width": asset.roi_width, "height": asset.roi_height}
        return {
            "id": asset.public_id, "asset_code": asset.asset_code, "asset_type": asset.asset_type,
            "name": asset.name, "location_desc": asset.location_desc,
            "factory_id": factory_id, "zone_id": zone_id, "zone_name": zone_name,
            "camera_id": camera_id, "camera_name": camera_name, "roi": roi,
            "has_reference": asset.reference_key is not None,
            "reference_captured_at": asset.reference_captured_at.isoformat() if asset.reference_captured_at else None,
            "reference_width": asset.reference_width, "reference_height": asset.reference_height,
            "check_interval_seconds": asset.check_interval_seconds,
            "change_after_seconds": asset.change_after_seconds,
            "similarity_threshold": asset.similarity_threshold,
            "monitoring_enabled": asset.monitoring_enabled,
            "monitoring_status": monitoring_status(asset, now),
            "last_state": asset.last_state, "last_similarity": asset.last_similarity,
            "last_checked_at": asset.last_checked_at.isoformat() if asset.last_checked_at else None,
            "version": asset.version,
        }

    @staticmethod
    def _audit_fields(asset):
        return {"asset_code": asset.asset_code, "asset_type": asset.asset_type, "name": asset.name,
                "location_desc": asset.location_desc,
                "roi": None if asset.roi_x is None else [asset.roi_x, asset.roi_y, asset.roi_width, asset.roi_height],
                "reference_sha256": asset.reference_sha256,
                "check_interval_seconds": asset.check_interval_seconds,
                "change_after_seconds": asset.change_after_seconds,
                "similarity_threshold": asset.similarity_threshold,
                "monitoring_enabled": asset.monitoring_enabled, "version": asset.version}

    async def _audit(self, action, asset, old, new):
        from src.modules.audit.application.services import AuditService
        await AuditService(self.db).record(enterprise_id=self.user.enterprise_id, user_id=self.user.user_id,
            action=action, entity_type="safety_asset", entity_id=asset.public_id, old_value=old, new_value=new)


def incident_dict(incident, asset, alert_id=None, alert_number=None, alert_status=None):
    return {
        "id": incident.public_id, "asset_id": asset.public_id, "asset_code": asset.asset_code,
        "asset_type": asset.asset_type,
        "kind": incident.kind, "similarity": incident.similarity, "scene_similarity": incident.scene_similarity,
        "has_snapshot": incident.snapshot_key is not None, "config_version": incident.config_version,
        "detected_at": incident.detected_at.isoformat(),
        "cleared_at": incident.cleared_at.isoformat() if incident.cleared_at else None,
        "alert_id": alert_id, "alert_number": alert_number, "alert_status": alert_status,
    }
