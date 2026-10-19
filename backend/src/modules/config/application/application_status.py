"""Current policy application is distinct from broker acceptance."""
from datetime import timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert

from src.modules.config.application.services import ConfigService
from src.shared.database.models import (
    AIWorker, Camera, CameraConfigApplication, CameraLease, ConfigDelivery, Enterprise, Zone, ZoneConfig,
)


async def acknowledge_configs(db, enterprise_id, worker_id, session_id, applications):
    # Lock in camera order, as assignment acquisition does. The lock spans
    # validation and upsert so an old owner cannot confirm after takeover.
    rows = (await db.execute(select(Camera, CameraLease, ZoneConfig.version, Zone.public_id).join(
        Enterprise, Enterprise.id == Camera.enterprise_id).join(
        AIWorker, AIWorker.id == Camera.worker_id).join(CameraLease,
        and_(CameraLease.camera_id == Camera.id, CameraLease.generation == Camera.assignment_generation)).join(
        ZoneConfig, and_(ZoneConfig.zone_id == Camera.zone_id, ZoneConfig.enterprise_id == Camera.enterprise_id))
        .join(Zone, Zone.id == Camera.zone_id).where(
        Enterprise.public_id == enterprise_id, AIWorker.worker_id == worker_id,
        AIWorker.enterprise_id == Camera.enterprise_id, AIWorker.deleted_at.is_(None), AIWorker.is_active.is_(True),
        Camera.public_id.in_([str(item.camera_id) for item in applications]),
        Camera.deleted_at.is_(None), Camera.is_active.is_(True),
    ).order_by(Camera.id).with_for_update(of=Camera))).all()
    now = await db.scalar(select(func.clock_timestamp()))
    by_camera = {str(item.camera_id): item for item in applications}
    values = []
    for camera, lease, version, zone_id in rows:
        item = by_camera[camera.public_id]
        if (lease.token != str(item.lease_token) or lease.session_id != session_id
                or lease.worker_id != camera.worker_id or lease.expires_at <= now or item.version != version
                or str(item.zone_id) != zone_id):
            continue
        values.append(dict(camera_id=camera.id, zone_id=camera.zone_id, version=version,
                           lease_token=lease.token, applied_at=now, confirmed_at=now))
    if values:
        statement = insert(CameraConfigApplication).values(values)
        incoming = statement.excluded
        same_application = and_(CameraConfigApplication.zone_id == incoming.zone_id,
            CameraConfigApplication.version == incoming.version, CameraConfigApplication.lease_token == incoming.lease_token)
        await db.execute(statement.on_conflict_do_update(index_elements=[CameraConfigApplication.camera_id],
            set_={"zone_id": incoming.zone_id, "version": incoming.version, "lease_token": incoming.lease_token,
                "confirmed_at": now, "applied_at": case((same_application, CameraConfigApplication.applied_at), else_=now)}))
    await db.commit()
    return {"accepted": len(values), "rejected": len(applications) - len(values)}


async def config_application_status(db, zone_id, enterprise_id):
    config = await ConfigService(db)._get_row(zone_id, enterprise_id)
    now = await db.scalar(select(func.clock_timestamp()))
    live = and_(CameraLease.worker_id == Camera.worker_id, CameraLease.expires_at > now)
    confirmed = and_(live, CameraConfigApplication.zone_id == Camera.zone_id,
        CameraConfigApplication.version == config.version,
        CameraConfigApplication.lease_token == CameraLease.token,
        CameraConfigApplication.confirmed_at > now - timedelta(seconds=90))
    total, applied, unassigned, last_applied = (await db.execute(select(
        func.count(Camera.id), func.count(Camera.id).filter(confirmed),
        func.count(Camera.id).filter(Camera.worker_id.is_(None)),
        func.max(CameraConfigApplication.applied_at).filter(confirmed),
    ).select_from(Camera).outerjoin(CameraLease,
        and_(CameraLease.camera_id == Camera.id, CameraLease.generation == Camera.assignment_generation))
        .outerjoin(CameraConfigApplication, CameraConfigApplication.camera_id == Camera.id).where(
        Camera.zone_id == config.zone_id, Camera.enterprise_id == config.enterprise_id,
        Camera.deleted_at.is_(None), Camera.is_active.is_(True), Camera.status != "Inactive",
    ))).one()
    delivery = await db.scalar(select(ConfigDelivery).where(
        ConfigDelivery.enterprise_id == config.enterprise_id, ConfigDelivery.zone_id == config.zone_id,
        ConfigDelivery.version == config.version))
    return {"zone_id": zone_id, "version": config.version,
        "status": "NoActiveCameras" if not total else "Applied" if total == applied else "Pending",
        "active_cameras": total, "applied_cameras": applied, "pending_cameras": total - applied,
        "unassigned_cameras": unassigned,
        "last_applied_at": last_applied.isoformat() if last_applied else None,
        "publication": {"status": delivery.status if delivery else "ReconciliationOnly",
            "attempts": delivery.attempts if delivery else 0,
            "next_attempt_at": delivery.next_attempt_at.isoformat() if delivery and delivery.status != "Published" else None,
            "published_at": delivery.published_at.isoformat() if delivery and delivery.published_at else None,
            "last_error": delivery.last_error if delivery else None}}
