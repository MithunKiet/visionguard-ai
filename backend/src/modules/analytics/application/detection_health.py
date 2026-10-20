"""Scoped current detection evidence; activation and heartbeat are not inference."""
from datetime import timedelta

from sqlalchemy import and_, case, func, or_, select

from src.shared.database.models import AIWorker, Camera, CameraConfigApplication, CameraLease, Enterprise, Factory, Zone, ZoneConfig
from src.shared.database.pid import to_pk
from src.shared.security.resource_policy import scoped_query

HEALTH_SECONDS = 60
PAUSED = ("Paused", "Maintenance")


async def detection_health(db, enterprise_id, scope, page=1, page_size=20, problems_only=False, zone_id=None):
    ent_pk = await to_pk(db, Enterprise, enterprise_id)
    now = await db.scalar(select(func.clock_timestamp()))
    cutoff = now - timedelta(seconds=HEALTH_SECONDS)
    applied = and_(CameraConfigApplication.zone_id == Camera.zone_id,
        CameraConfigApplication.version == ZoneConfig.version, CameraConfigApplication.lease_token == CameraLease.token)
    state = case(
        (or_(Camera.status == "Inactive", Camera.is_active.is_(False), Factory.is_active.is_(False),
            Factory.deleted_at.is_not(None), Factory.status != "Active", Zone.is_active.is_(False),
            Zone.deleted_at.is_not(None), Zone.status != "Active"), "Paused"),
        (and_(Camera.in_maintenance.is_(True), or_(Camera.maintenance_until.is_(None), Camera.maintenance_until > now)), "Maintenance"),
        (Camera.worker_id.is_(None), "Unassigned"),
        (or_(AIWorker.id.is_(None), AIWorker.deleted_at.is_not(None), AIWorker.is_active.is_(False),
            AIWorker.status != "Online", AIWorker.last_heartbeat.is_(None), AIWorker.last_heartbeat <= cutoff), "WorkerUnavailable"),
        (or_(CameraLease.token.is_(None), CameraLease.worker_id != Camera.worker_id, CameraLease.expires_at <= now), "LeaseExpired"),
        (or_(CameraConfigApplication.camera_id.is_(None), ZoneConfig.id.is_(None), ~applied), "ConfigPending"),
        (or_(CameraConfigApplication.health_reported_at.is_(None), CameraConfigApplication.health_reported_at <= cutoff), "TelemetryMissing"),
        (or_(CameraConfigApplication.last_inference_at.is_(None), CameraConfigApplication.last_inference_at <= cutoff),
            case((Camera.status == "Offline", "StreamOffline"), else_="InferenceStale")),
        else_="Detecting",
    ).label("state")
    query = select(Camera.public_id.label("camera_id"), Camera.name.label("camera_name"), Camera.code,
        Factory.public_id.label("factory_id"), Factory.name.label("factory_name"),
        Zone.public_id.label("zone_id"), Zone.name.label("zone_name"), state,
        CameraConfigApplication.health_reported_at, CameraConfigApplication.last_inference_at,
    ).select_from(Camera).join(Factory, and_(Factory.id == Camera.factory_id, Factory.enterprise_id == ent_pk)).join(
        Zone, and_(Zone.id == Camera.zone_id, Zone.enterprise_id == ent_pk)).outerjoin(
        AIWorker, and_(AIWorker.id == Camera.worker_id, AIWorker.enterprise_id == ent_pk)).outerjoin(
        CameraLease, and_(CameraLease.camera_id == Camera.id, CameraLease.generation == Camera.assignment_generation)).outerjoin(
        ZoneConfig, and_(ZoneConfig.zone_id == Camera.zone_id, ZoneConfig.enterprise_id == ent_pk)).outerjoin(
        CameraConfigApplication, CameraConfigApplication.camera_id == Camera.id).where(
            Camera.enterprise_id == ent_pk, Camera.deleted_at.is_(None))
    if zone_id:
        query = query.where(Camera.zone_id == await to_pk(db, Zone, zone_id))
    query = await scoped_query(db, query, Camera, scope=scope)
    cameras = query.subquery()
    counts = dict((await db.execute(select(cameras.c.state, func.count()).group_by(cameras.c.state))).all())
    total = sum(counts.values())
    paused = sum(counts.get(state, 0) for state in PAUSED)
    expected = total - paused
    detecting = counts.get("Detecting", 0)
    gaps = expected - detecting
    filtered = select(cameras)
    filtered_total = total
    if problems_only:
        filtered = filtered.where(cameras.c.state.not_in([*PAUSED, "Detecting"]))
        filtered_total = gaps
    rows = (await db.execute(filtered.order_by(cameras.c.camera_name, cameras.c.camera_id)
        .offset((page - 1) * page_size).limit(page_size))).mappings().all()
    return {"checked_at": now.isoformat(), "valid_for_seconds": 15,
        "summary": {"total_cameras": total, "expected_cameras": expected, "detecting_cameras": detecting,
            "gap_cameras": gaps, "paused_cameras": paused, "states": counts,
            "status": "NoMonitoringExpected" if not expected else "DetectionGap" if gaps else "RecentInferenceObserved"},
        "cameras": [{**row, "health_reported_at": row["health_reported_at"].isoformat() if row["health_reported_at"] else None,
            "last_inference_at": row["last_inference_at"].isoformat() if row["last_inference_at"] else None} for row in rows],
        "total": filtered_total}
