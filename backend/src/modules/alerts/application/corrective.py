"""Corrective plans, immutable photo attachments and transactional history."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io
from pathlib import PurePath
from uuid import uuid4

from minio import Minio
from PIL import Image
from sqlalchemy import and_, func, or_, select
import urllib3

from src.core.exceptions import ForbiddenException, NotFoundException, VisionGuardException
from src.core.settings import settings
from src.shared.database.models import Alert, AlertHistory, CorrectiveEvidence, Enterprise, Role, User, UserRole
from src.shared.security.resource_policy import scoped_query

REVIEW_ROLES = ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER")
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def history(db, alert, actor, event_type, comment, details=None):
    db.add(AlertHistory(alert_id=alert.id, created_by=actor, event_type=event_type,
        from_status=alert.status, to_status=alert.status, comment=comment, details=details))


def eligible_users(alert):
    def has_roles(codes):
        return select(UserRole.user_public_id).join(Role, Role.public_id == UserRole.role_public_id).where(
            UserRole.user_public_id == User.public_id, Role.code.in_(codes)).exists()
    return select(User).where(User.enterprise_id == alert.enterprise_id, User.deleted_at.is_(None),
        User.is_active.is_(True), User.status == "Active", or_(has_roles(("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
            and_(User.factory_id == alert.factory_id, has_roles(("FACTORY_MANAGER", "SAFETY_OFFICER")))))


async def validate_assignee(db, alert, public_id, actor=None):
    query = eligible_users(alert).where(User.public_id == public_id)
    query = await scoped_query(db, query, User, user=actor)
    user = await db.scalar(query)
    if user is None:
        raise VisionGuardException("INVALID_ASSIGNEE", "Choose an active reviewer who can access this incident", 422)
    return user


async def ensure_photo_capacity(db, alert):
    count = await db.scalar(select(func.count()).select_from(CorrectiveEvidence).where(CorrectiveEvidence.alert_id == alert.id))
    if count >= 50:
        raise VisionGuardException("EVIDENCE_LIMIT", "This incident has 50 corrective photos; keep its existing plan and evidence", 422)


def verify_photo(content):
    if not content or len(content) > MAX_PHOTO_BYTES:
        raise VisionGuardException("INVALID_PHOTO", "Choose a JPEG or PNG photo up to 5 MiB", 422)
    try:
        with Image.open(io.BytesIO(content)) as image:
            fmt = image.format
            if fmt not in {"JPEG", "PNG"} or image.width * image.height > 20_000_000 or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Unsupported image")
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except Exception:
        raise VisionGuardException("INVALID_PHOTO", "Choose a valid JPEG or PNG photo up to 20 megapixels", 422)
    return "image/jpeg" if fmt == "JPEG" else "image/png"


def photo_client():
    return Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY, secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE, region="us-east-1", http_client=urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=2, read=10), retries=urllib3.Retry(total=0)))


async def store_photo(key, content, content_type):
    try:
        await asyncio.wait_for(asyncio.to_thread(photo_client().put_object, settings.MINIO_BUCKET_SNAPSHOTS,
            key, io.BytesIO(content), len(content), content_type=content_type), timeout=20)
    except Exception:
        raise VisionGuardException("EVIDENCE_STORAGE_UNAVAILABLE", "Evidence storage is unavailable; retry the upload", 503)


async def read_photo(key):
    def read():
        response = photo_client().get_object(settings.MINIO_BUCKET_SNAPSHOTS, key)
        try:
            return response.read(MAX_PHOTO_BYTES + 1)
        finally:
            response.close()
            response.release_conn()
    try:
        return await asyncio.wait_for(asyncio.to_thread(read), timeout=20)
    except Exception:
        raise VisionGuardException("EVIDENCE_STORAGE_UNAVAILABLE", "Evidence is unavailable; retry later", 503)


class CorrectiveActionService:
    def __init__(self, db, user):
        self.db, self.user = db, user

    async def _alert(self, alert_id, lock=False):
        query = await scoped_query(self.db, select(Alert).join(Enterprise, Enterprise.id == Alert.enterprise_id).where(
            Alert.public_id == alert_id, Enterprise.public_id == self.user.enterprise_id, Alert.deleted_at.is_(None)),
            Alert, user=self.user)
        if lock:
            query = query.with_for_update(of=Alert).execution_options(populate_existing=True)
        alert = await self.db.scalar(query)
        if alert is None:
            raise NotFoundException("Alert", alert_id)
        return alert

    @staticmethod
    def editable(alert, revision):
        if alert.status not in {"Open", "Acknowledged"}:
            raise VisionGuardException("INCIDENT_CLOSED", "Closed incidents cannot be changed", 409)
        if revision != alert.action_revision:
            raise VisionGuardException("ACTION_CONFLICT", "The action changed. Refresh and check it before retrying", 409)

    async def get(self, alert_id):
        alert = await self._alert(alert_id)
        owner = await self.db.scalar(select(User).where(User.id == alert.assigned_to, User.enterprise_id == alert.enterprise_id))
        evidence = (await self.db.scalars(select(CorrectiveEvidence).where(
            CorrectiveEvidence.alert_id == alert.id, CorrectiveEvidence.enterprise_id == alert.enterprise_id)
            .order_by(CorrectiveEvidence.created_at, CorrectiveEvidence.id).limit(50))).all()
        state = "Completed" if alert.action_completed_at else "Cancelled" if alert.action_description and alert.status == "FalsePositive" else "Planned" if alert.action_description else "NotPlanned"
        return {"revision": alert.action_revision, "plan_version": alert.action_plan_version,
            "description": alert.action_description, "assigned_to": owner.public_id if owner else None,
            "assignee_name": owner.name if owner else None,
            "assignee_active": bool(owner and owner.status == "Active" and owner.deleted_at is None and owner.is_active),
            "due_at": alert.action_due_at.isoformat() if alert.action_due_at else None,
            "completed_at": alert.action_completed_at.isoformat() if alert.action_completed_at else None,
            "status": state, "overdue": bool(state == "Planned" and alert.action_due_at and alert.action_due_at < datetime.now(timezone.utc)),
            "evidence": [{"id": row.public_id, "filename": row.filename, "size_bytes": row.size_bytes,
                "sha256": row.sha256, "plan_version": row.plan_version, "current_plan": row.plan_version == alert.action_plan_version,
                "created_at": row.created_at.isoformat(), "uploaded_by": row.created_by} for row in evidence]}

    async def assignees(self, alert_id, search, page, page_size):
        alert = await self._alert(alert_id)
        query = await scoped_query(self.db, eligible_users(alert), User, user=self.user)
        if search:
            query = query.where(User.name.icontains(search, autoescape=True))
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        users = (await self.db.scalars(query.order_by(User.name, User.id).offset((page - 1) * page_size).limit(page_size))).all()
        return [{"id": user.public_id, "name": user.name} for user in users], total

    async def plan(self, alert_id, body):
        alert = await self._alert(alert_id, lock=True)
        self.editable(alert, body.expected_revision)
        now = datetime.now(timezone.utc)
        if not now < body.due_at <= now + timedelta(days=366):
            raise VisionGuardException("INVALID_DUE_DATE", "Choose a future due date within 366 days", 422)
        owner = await validate_assignee(self.db, alert, str(body.assigned_to), self.user)
        await ensure_photo_capacity(self.db, alert)
        old = {"description": alert.action_description, "due_at": alert.action_due_at.isoformat() if alert.action_due_at else None,
            "plan_version": alert.action_plan_version, "completion_invalidated": alert.action_completed_at is not None}
        alert.assigned_to, alert.action_description, alert.action_due_at = owner.id, body.description, body.due_at
        alert.action_completed_at = None
        alert.action_revision += 1
        alert.action_plan_version += 1
        history(self.db, alert, self.user.user_id, "ACTION_PLANNED", f"Corrective plan assigned to {owner.name}; due {body.due_at.isoformat()}",
            {"previous": old, "assigned_to": owner.public_id, "description": body.description, "due_at": body.due_at.isoformat(),
                "plan_version": alert.action_plan_version})
        await self.db.commit()
        return await self.get(alert_id)

    async def upload(self, alert_id, revision, upload_id, filename, content):
        alert = await self._alert(alert_id)
        digest = hashlib.sha256(content).hexdigest()
        existing = await self.db.scalar(select(CorrectiveEvidence).where(CorrectiveEvidence.public_id == upload_id))
        if existing:
            if existing.alert_id != alert.id or existing.enterprise_id != alert.enterprise_id or existing.sha256 != digest:
                raise VisionGuardException("UPLOAD_CONFLICT", "This upload reference was already used", 409)
            return await self.get(alert_id)
        self.editable(alert, revision)
        if not alert.action_description or alert.action_completed_at:
            raise VisionGuardException("ACTION_NOT_EDITABLE", "Save an incomplete corrective plan before adding photos", 409)
        await ensure_photo_capacity(self.db, alert)
        content_type = await asyncio.to_thread(verify_photo, content)
        enterprise_id, plan_version = self.user.enterprise_id, alert.action_plan_version
        key = f"{enterprise_id}/corrective/{alert_id}/{upload_id}/{uuid4()}"
        await self.db.rollback()  # Do not hold a database connection during storage I/O.
        await store_photo(key, content, content_type)
        alert = await self._alert(alert_id, lock=True)
        self.editable(alert, revision)
        if alert.action_plan_version != plan_version or alert.action_completed_at:
            raise VisionGuardException("ACTION_CONFLICT", "The corrective plan changed; refresh before retrying", 409)
        await ensure_photo_capacity(self.db, alert)
        name = PurePath((filename or "photo").replace("\\", "/")).name
        name = "".join(char for char in name if char.isprintable())[:200] or "photo"
        self.db.add(CorrectiveEvidence(public_id=upload_id, enterprise_id=alert.enterprise_id, alert_id=alert.id,
            plan_version=plan_version, object_key=key, filename=name, content_type=content_type, size_bytes=len(content),
            sha256=digest, created_by=self.user.user_id))
        alert.action_revision += 1
        history(self.db, alert, self.user.user_id, "EVIDENCE_ADDED", f"Corrective photo attached: {name}",
            {"evidence_id": upload_id, "sha256": digest, "plan_version": plan_version})
        await self.db.commit()
        return await self.get(alert_id)

    async def complete(self, alert_id, body):
        alert = await self._alert(alert_id, lock=True)
        self.editable(alert, body.expected_revision)
        if not alert.action_description or alert.action_completed_at:
            raise VisionGuardException("ACTION_NOT_EDITABLE", "An incomplete corrective plan is required", 409)
        actor_pk = await self.db.scalar(select(User.id).where(User.public_id == self.user.user_id))
        if actor_pk != alert.assigned_to and not set(self.user.roles) & {"SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER"}:
            raise ForbiddenException("Only the assignee or a scoped administrator/manager can complete this action")
        evidence = await self.db.scalar(select(CorrectiveEvidence.id).where(CorrectiveEvidence.alert_id == alert.id,
            CorrectiveEvidence.plan_version == alert.action_plan_version).limit(1))
        if evidence is None:
            raise VisionGuardException("EVIDENCE_REQUIRED", "Attach a corrective photo for the current plan before completing it", 422)
        alert.action_completed_at = datetime.now(timezone.utc)
        alert.action_revision += 1
        history(self.db, alert, self.user.user_id, "ACTION_COMPLETED", body.note, {"plan_version": alert.action_plan_version})
        await self.db.commit()
        return await self.get(alert_id)

    async def photo(self, alert_id, evidence_id):
        alert = await self._alert(alert_id)
        photo = await self.db.scalar(select(CorrectiveEvidence).where(CorrectiveEvidence.public_id == evidence_id,
            CorrectiveEvidence.alert_id == alert.id, CorrectiveEvidence.enterprise_id == alert.enterprise_id))
        if photo is None:
            raise NotFoundException("Evidence", evidence_id)
        key, content_type, digest, size = photo.object_key, photo.content_type, photo.sha256, photo.size_bytes
        await self.db.rollback()
        content = await read_photo(key)
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise VisionGuardException("EVIDENCE_INTEGRITY", "Evidence could not be verified; contact an administrator", 503)
        return content, content_type
