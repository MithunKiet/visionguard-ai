"""Worker asset events: durable incidents with evidence, plus status telemetry."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
import structlog

from src.shared.database.models import Alert, AssetIncident, Camera, Enterprise, Factory, SafetyAsset, Zone

log = structlog.get_logger()

# Routing key → (incident kind, alert type, severity). None = clears incidents.
INCIDENT_ROUTES = {
    "events.asset_area_changed": ("AREA_CHANGED", "SAFETY_ASSET_AREA_CHANGED", "High"),
    "events.asset_view_changed": ("VIEW_CHANGED", "SAFETY_ASSET_VIEW_CHANGED", "Medium"),
    "events.asset_restored": None,
}
_STATES = {"OK", "Changed", "ViewChanged", "Occluded"}


def _observed_at(body):
    if body.get("timestamp"):
        value = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
        if value.tzinfo is not None:
            return value
    return datetime.now(timezone.utc)


def _score(value):
    if value is None:
        return None
    value = float(value)
    if not -1.0 <= value <= 1.0:
        raise ValueError("Similarity out of range")
    return value


async def _owned_asset(db, body, lock=False):
    """The asset must belong to the event's camera, zone and enterprise."""
    query = (select(SafetyAsset).join(Camera, Camera.id == SafetyAsset.camera_id)
        .join(Enterprise, Enterprise.id == SafetyAsset.enterprise_id)
        .join(Zone, Zone.id == SafetyAsset.zone_id).join(Factory, Factory.id == SafetyAsset.factory_id)
        .where(SafetyAsset.public_id == str(UUID(body["asset_id"])), Camera.public_id == body["camera_id"],
               Enterprise.public_id == body["enterprise_id"], Zone.public_id == body["zone_id"],
               Factory.public_id == body["factory_id"]))
    if lock:
        query = query.with_for_update(of=SafetyAsset)
    return await db.scalar(query)


async def handle_asset_incident(routing_key: str, body: dict) -> None:
    from src.modules.alerts.application.services import AlertService
    from src.modules.alerts.infrastructure.repositories import AlertRepository
    from src.modules.maintenance.application.services import MaintenanceService
    from src.modules.worker.infrastructure.leases import fence_camera_event
    from src.shared.database.session import AsyncSessionFactory
    from src.shared.messaging.consumer import _claim_alert_event

    required = ("event_id", "enterprise_id", "factory_id", "zone_id", "camera_id", "asset_id")
    if not all(body.get(key) for key in required):
        raise ValueError("Asset event is missing required fields")
    route = INCIDENT_ROUTES[routing_key]
    observed_at = _observed_at(body)
    async with AsyncSessionFactory() as db:
        db.info["defer_commit"] = True
        async with db.begin():
            if not await _claim_alert_event(db, body):
                return
            await fence_camera_event(db, body, historical=True)
            asset = await _owned_asset(db, body, lock=True)
            if asset is None:
                raise ValueError("Asset event ownership mismatch")
            if asset.deleted_at is not None:
                log.info("asset_event.deleted_asset", asset_id=asset.public_id)
                return
            if route is None:
                await db.execute(update(AssetIncident).where(AssetIncident.asset_id == asset.id,
                    AssetIncident.cleared_at.is_(None), AssetIncident.detected_at <= observed_at)
                    .values(cleared_at=observed_at))
                return
            kind, alert_type, severity = route
            # Evidence is served by key, so it must sit under this camera's prefix.
            prefix = "/".join(str(body[name]) for name in ("enterprise_id", "factory_id", "zone_id", "camera_id")) + "/"
            snapshot_key = body.get("snapshot_key")
            if snapshot_key is not None and (not isinstance(snapshot_key, str) or not snapshot_key.startswith(prefix)
                                             or ".." in snapshot_key or len(snapshot_key) > 500):
                raise ValueError("Asset evidence key outside its camera prefix")
            incident = AssetIncident(enterprise_id=asset.enterprise_id, asset_id=asset.id, camera_id=asset.camera_id,
                event_id=str(UUID(body["event_id"])), kind=kind, similarity=_score(body.get("similarity")),
                scene_similarity=_score(body.get("scene_similarity")), snapshot_key=snapshot_key,
                config_version=body.get("config_version"), detected_at=observed_at)
            db.add(incident)
            db.info["enterprise_id"] = body["enterprise_id"]
            if await MaintenanceService.is_in_maintenance(db, body["camera_id"]):
                return
            # One live alert per asset and kind: a flapping area adds incidents
            # (with evidence) to the open alert instead of paging again.
            open_alert = await db.scalar(select(Alert.id).join(AssetIncident, AssetIncident.alert_id == Alert.id)
                .where(AssetIncident.asset_id == asset.id, AssetIncident.kind == kind,
                       Alert.status.in_(["Open", "Acknowledged"])).limit(1))
            if open_alert is None:
                alert = await AlertService(AlertRepository(db)).create_event_alert(
                    enterprise_id=body["enterprise_id"], factory_id=body["factory_id"], zone_id=body["zone_id"],
                    camera_id=body["camera_id"], alert_type=alert_type, severity=severity, cooldown_seconds=0)
                open_alert = await db.scalar(select(Alert.id).where(Alert.public_id == alert.id))
            incident.alert_id = open_alert
        db.info["defer_commit"] = False


async def handle_asset_status(body: dict) -> None:
    """Latest observation per asset; current lease only (not historical replay)."""
    from src.modules.worker.infrastructure.leases import fence_camera_event
    from src.shared.database.session import AsyncSessionFactory

    if not (body.get("camera_id") and body.get("enterprise_id") and isinstance(body.get("assets"), list)):
        log.warning("asset_status.missing_fields")
        return
    checked_at = _observed_at(body)
    async with AsyncSessionFactory() as db:
        async with db.begin():
            await fence_camera_event(db, body)
            camera_pk = await db.scalar(select(Camera.id).join(Enterprise, Enterprise.id == Camera.enterprise_id)
                .where(Camera.public_id == body["camera_id"], Enterprise.public_id == body["enterprise_id"]))
            if camera_pk is None:
                raise ValueError("Asset status ownership mismatch")
            for entry in body["assets"][:200]:
                state = entry.get("state")
                if state not in _STATES:
                    continue
                # Telemetry may arrive out of order; never move an asset backwards.
                await db.execute(update(SafetyAsset).where(
                    SafetyAsset.public_id == str(UUID(entry["asset_id"])), SafetyAsset.camera_id == camera_pk,
                    SafetyAsset.deleted_at.is_(None),
                    (SafetyAsset.last_checked_at.is_(None)) | (SafetyAsset.last_checked_at < checked_at))
                    .values(last_state=state, last_similarity=_score(entry.get("similarity")), last_checked_at=checked_at))
