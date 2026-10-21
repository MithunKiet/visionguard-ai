"""Bounded CSV preview and atomic, replay-safe camera registration."""
import csv
import hashlib
import hmac
import io
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from sqlalchemy import select, text

from src.core.exceptions import VisionGuardException
from src.core.settings import settings
from src.shared.database.models import AuditLog, Camera, CameraImport, Enterprise, Factory, User, Zone
from src.shared.security.camera_url import validate_rtsp_url
from src.shared.security.resource_policy import scoped_query

MAX_BYTES = 512 * 1024
MAX_ROWS = 200
REQUIRED = {"name", "code", "zone_id", "rtsp_url"}
OPTIONAL = {"factory_id", "fps", "camera_type", "position_desc"}


def fail(message, status=422):
    raise VisionGuardException("CAMERA_IMPORT_INVALID", message, status)


def fingerprint(text):
    return hmac.new(settings.JWT_SECRET.encode(), ("camera-import-v1:" + text).encode(), hashlib.sha256).hexdigest()


def stream_identity(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or (554 if parsed.scheme == "rtsp" else 322), parsed.path, parsed.query)


def parse_csv(text):
    if not isinstance(text, str) or len(text.encode()) > MAX_BYTES or "\x00" in text:
        fail("CSV must be UTF-8 text no larger than 512 KiB")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not REQUIRED <= set(fields) or set(fields) - REQUIRED - OPTIONAL:
            fail("CSV needs name,code,zone_id,rtsp_url; optional: factory_id,fps,camera_type,position_desc")
        rows = []
        for number, raw in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                fail("Import at most 200 cameras per batch")
            errors = []
            if None in raw or any(value is None for value in raw.values()):
                errors.append("Column count does not match the header")
            row = {key: (raw.get(key) or "").strip() for key in REQUIRED | OPTIONAL}
            for field, limit in [("name", 200), ("code", 50), ("rtsp_url", 500)]:
                if not row[field] or len(row[field]) > limit:
                    errors.append(f"{field} must contain 1–{limit} characters")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,49}", row["code"]):
                errors.append("code must use letters, digits, underscore, dot or hyphen")
            for field in ("zone_id", "factory_id"):
                try:
                    if row[field] or field == "zone_id":
                        row[field] = str(UUID(row[field]))
                except ValueError:
                    errors.append(f"{field} must be a public UUID")
            try:
                if any(ord(char) < 32 for char in row["rtsp_url"]):
                    raise ValueError()
                validate_rtsp_url(row["rtsp_url"])
            except ValueError:
                errors.append("RTSP URL is invalid or its host is not allowed")
            try:
                row["fps"] = float(row["fps"]) if row["fps"] else None
                if row["fps"] is not None and (not math.isfinite(row["fps"]) or not 0.1 <= row["fps"] <= 30):
                    raise ValueError()
            except ValueError:
                row["fps"] = None
                errors.append("fps must be a finite number from 0.1 to 30")
            row["camera_type"] = row["camera_type"] or "Fixed"
            if row["camera_type"] not in {"Fixed", "PTZ", "Fisheye"}:
                errors.append("camera_type must be Fixed, PTZ or Fisheye")
            if len(row["position_desc"]) > 300:
                errors.append("position_desc exceeds 300 characters")
            rows.append({**row, "row": number, "errors": errors})
    except (csv.Error, UnicodeError):
        fail("Malformed CSV; check quoting and UTF-8 encoding")
    if not rows:
        fail("CSV contains no camera rows")
    return rows


async def lock_inventory(db, enterprise_id):
    # All normal and bulk creation paths take this same transaction lock.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "camera-inventory:" + enterprise_id})
    entity = await db.scalar(select(Enterprise).where(Enterprise.public_id == enterprise_id, Enterprise.deleted_at.is_(None)))
    if entity is None:
        fail("Enterprise is unavailable", 403)
    return entity.id


async def registered(db, enterprise_pk, exclude_id=None):
    query = select(Camera.code, Camera.rtsp_url).where(Camera.enterprise_id == enterprise_pk, Camera.deleted_at.is_(None))
    if exclude_id:
        query = query.where(Camera.public_id != exclude_id)
    rows = (await db.execute(query)).all()
    codes = {code.casefold() for code, _ in rows}
    streams = set()
    for _, url in rows:
        try:
            streams.add(stream_identity(url))
        except ValueError:
            continue  # Legacy malformed URLs do not prevent valid camera registration.
    return codes, streams


async def check_rows(db, user, rows, enterprise_pk, *, lock=False):
    query = select(Zone, Factory.public_id, Factory.name).join(Factory, Factory.id == Zone.factory_id).where(
        Zone.public_id.in_({row["zone_id"] for row in rows}), Zone.enterprise_id == enterprise_pk,
        Zone.deleted_at.is_(None), Zone.is_active.is_(True), Zone.status == "Active",
        Factory.enterprise_id == enterprise_pk, Factory.deleted_at.is_(None), Factory.is_active.is_(True), Factory.status == "Active")
    query = await scoped_query(db, query, Zone, user)
    if lock:
        query = query.with_for_update(of=(Zone, Factory), read=True)
    zones = {zone.public_id: (zone, factory_id, factory_name) for zone, factory_id, factory_name in (await db.execute(query)).all()}
    codes, streams = await registered(db, enterprise_pk)
    seen_codes, seen_streams = set(), set()
    for row in rows:
        zone = zones.get(row["zone_id"])
        if not zone:
            row["errors"].append("Zone unavailable or outside your access")
        elif row["factory_id"] and row["factory_id"] != zone[1]:
            row["errors"].append("Factory does not match the zone")
        if row["code"].casefold() in codes:
            row["errors"].append("Camera code already registered in this enterprise")
        if row["code"].casefold() in seen_codes:
            row["errors"].append("Duplicate camera code in this CSV")
        seen_codes.add(row["code"].casefold())
        try:
            stream = stream_identity(row["rtsp_url"])
            if stream in streams:
                row["errors"].append("Camera stream already registered in this enterprise")
            if stream in seen_streams:
                row["errors"].append("Duplicate camera stream in this CSV")
            seen_streams.add(stream)
        except ValueError:
            pass
    return zones


def public_rows(rows, zones):
    return [{"row": row["row"], "name": row["name"], "code": row["code"], "zone_id": row["zone_id"],
             "zone_name": zones[row["zone_id"]][0].name if row["zone_id"] in zones else None,
             "factory_name": zones[row["zone_id"]][2] if row["zone_id"] in zones else None,
             "fps": row["fps"], "errors": row["errors"]} for row in rows]


async def preview(db, user, text):
    rows = parse_csv(text)
    enterprise_pk = await db.scalar(select(Enterprise.id).where(Enterprise.public_id == user.enterprise_id))
    zones = await check_rows(db, user, rows, enterprise_pk)
    valid = all(not row["errors"] for row in rows)
    token = None
    if valid:
        token = jwt.encode({"type": "camera_import", "sub": user.user_id, "enterprise_id": user.enterprise_id,
                            "digest": fingerprint(text), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                           settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return {"valid": valid, "rows": public_rows(rows, zones), "preview_token": token, "expires_in": 600 if valid else 0}


async def commit(db, user, text, preview_token, request_key):
    try:
        request_key = str(UUID(request_key))
    except (ValueError, TypeError, AttributeError):
        fail("request_key must be a UUID")
    digest = fingerprint(text)
    enterprise_pk = await lock_inventory(db, user.enterprise_id)
    existing = await db.scalar(select(CameraImport).where(CameraImport.enterprise_id == enterprise_pk, CameraImport.request_key == request_key))
    if existing:
        if existing.actor_id != user.user_id or not hmac.compare_digest(existing.payload_hash, digest):
            fail("Import request key is already used by another request", 409)
        visible = await scoped_query(db, select(Camera.public_id).where(Camera.enterprise_id == enterprise_pk,
            Camera.public_id.in_([row["id"] for row in existing.result["cameras"]]), Camera.deleted_at.is_(None)), Camera, user)
        if len((await db.scalars(visible)).all()) != len(existing.result["cameras"]):
            fail("Import result is no longer accessible", 404)
        return {**existing.result, "replayed": True}
    try:
        payload = jwt.decode(preview_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                             options={"require": ["exp", "sub", "enterprise_id", "digest", "type"]})
        if payload["type"] != "camera_import" or payload["sub"] != user.user_id or payload["enterprise_id"] != user.enterprise_id or not hmac.compare_digest(payload["digest"], digest):
            raise ValueError()
    except (jwt.InvalidTokenError, ValueError, TypeError):
        fail("Preview expired or changed; preview this CSV again", 409)
    rows = parse_csv(text)
    zones = await check_rows(db, user, rows, enterprise_pk, lock=True)
    if any(row["errors"] for row in rows):
        fail("Camera inventory or access changed; preview the CSV again", 409)
    result = {"request_key": request_key, "replayed": False, "cameras": []}
    created = []
    for row in rows:
        zone = zones[row["zone_id"]][0]
        camera = Camera(enterprise_id=enterprise_pk, factory_id=zone.factory_id, zone_id=zone.id,
            name=row["name"], code=row["code"], rtsp_url=row["rtsp_url"], camera_type=row["camera_type"],
            fps=row["fps"], position_desc=row["position_desc"] or None, status="Inactive", is_active=False,
            created_by=user.user_id, ppe_overrides={})
        db.add(camera)
        created.append((camera, row))
    await db.flush()
    for camera, row in created:
        result["cameras"].append({"id": camera.public_id, "row": row["row"], "name": row["name"], "code": row["code"],
                                  "zone_id": row["zone_id"], "status_at_import": "Inactive"})
    db.add(CameraImport(enterprise_id=enterprise_pk, actor_id=user.user_id, request_key=request_key, payload_hash=digest, result=result))
    actor_pk = await db.scalar(select(User.id).where(User.public_id == user.user_id))
    db.add(AuditLog(enterprise_id=enterprise_pk, user_id=actor_pk, action="CAMERAS_IMPORTED", entity_type="camera_import", entity_id=request_key,
                   new_value={"actor_id": user.user_id, "camera_ids": [row["id"] for row in result["cameras"]]}))
    await db.commit()
    return result
