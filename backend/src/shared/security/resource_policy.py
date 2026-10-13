"""Shared authorization for resource references in authenticated HTTP routes."""
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, NotFoundException
from src.shared.database import models as m
from src.shared.database.pid import to_pk
from src.shared.database.session import get_db
from src.shared.security.dependencies import AuthUser, get_current_user
from src.shared.security.scope import apply_factory_scope, apply_zone_scope, get_scope

_MODELS = {
    "factory_id": m.Factory, "department_id": m.Department, "zone_id": m.Zone,
    "camera_id": m.Camera, "user_id": m.User, "plant_head_id": m.User,
    "head_user_id": m.User, "supervisor_id": m.User, "assigned_to": m.User,
    "shift_id": m.Shift, "maintenance_id": m.CameraMaintenance,
    "recipient_id": m.NotificationRecipient, "worker_id": m.AIWorker,
    "alert_id": m.Alert, "violation_id": m.PPEViolation,
}


async def scoped_query(db, query, model, user=None, *, scope=None):
    if scope is None:
        scope = get_scope(user) if user else db.info.get("scope")
    if scope is None or scope.unrestricted:
        return query
    if model is m.Factory:
        return await apply_factory_scope(db, query, scope, m.Factory.id)
    if model is m.Zone:
        return await apply_zone_scope(db, query, scope, m.Zone.factory_id, m.Zone.id)
    if hasattr(model, "factory_id") and hasattr(model, "zone_id"):
        return await apply_zone_scope(db, query, scope, model.factory_id, model.zone_id)
    if hasattr(model, "zone_id"):
        zones = await apply_zone_scope(db, select(m.Zone.id), scope, m.Zone.factory_id, m.Zone.id)
        return query.where(model.zone_id.in_(zones))
    if hasattr(model, "camera_id"):
        cameras = await apply_zone_scope(db, select(m.Camera.id), scope, m.Camera.factory_id, m.Camera.zone_id)
        return query.where(model.camera_id.in_(cameras))
    if hasattr(model, "factory_id"):
        return await apply_factory_scope(db, query, scope, model.factory_id)
    return query


async def require_reference(db, model, public_id, user):
    pk = await to_pk(db, model, str(public_id))
    query = await scoped_query(db, select(model).where(model.id == pk), model, user)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise NotFoundException(model.__name__, str(public_id))
    return row


async def enforce_resource_scope(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check detail paths and submitted references before any service mutates state.

    Collection queries separately use scoped_query; this dependency must never
    substitute for filtering a list or aggregate query.
    """
    db.info["scope"] = get_scope(user)
    values = dict(request.query_params)
    values.update(request.path_params)
    body = {}
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
    # Check path and body separately: a submitted ID cannot shadow a path ID.
    resolved = {}
    for references in (values, body):
        for key, model in _MODELS.items():
            value = references.get(key)
            if value is not None:
                resolved[key] = await require_reference(db, model, value, user)
        for zone_id in references.get("assigned_zone_ids", []) or []:
            zone = await require_reference(db, m.Zone, zone_id, user)
            if resolved.get("factory_id") and zone.factory_id != resolved["factory_id"].id:
                raise ForbiddenException("Assigned zone is outside the selected factory")
            if resolved.get("department_id") and zone.department_id != resolved["department_id"].id:
                raise ForbiddenException("Assigned zone is outside the selected department")
    if request.method in {"PUT", "PATCH"} and request.path_params.get("user_id"):
        target = resolved["user_id"]
        factory_pk = resolved["factory_id"].id if body.get("factory_id") else (None if "factory_id" in body else target.factory_id)
        department_pk = resolved["department_id"].id if body.get("department_id") else (None if "department_id" in body else target.department_id)
        if department_pk:
            parent = await db.scalar(select(m.Department.factory_id).where(m.Department.id == department_pk))
            if factory_pk is None or parent != factory_pk:
                raise ForbiddenException("User department must belong to the selected factory")
        for zone_id in body.get("assigned_zone_ids", target.assigned_zone_ids) or []:
            assigned = await require_reference(db, m.Zone, zone_id, user)
            if (factory_pk and assigned.factory_id != factory_pk) or (department_pk and assigned.department_id != department_pk):
                raise ForbiddenException("User zone assignment does not match the user hierarchy")
    factory = resolved.get("factory_id")
    department = resolved.get("department_id")
    zone = resolved.get("zone_id")
    if factory and department and department.factory_id != factory.id:
        raise ForbiddenException("Department is outside the selected factory")
    if factory and zone and zone.factory_id != factory.id:
        raise ForbiddenException("Zone is outside the selected factory")
    if department and zone and zone.department_id != department.id:
        raise ForbiddenException("Zone is outside the selected department")
    scope = get_scope(user)
    path = request.url.path
    if not scope.unrestricted:
        # These records represent enterprise-wide information/settings. Their
        # schema currently has no durable factory/zone scope.
        if path.startswith(("/api/v1/reports", "/api/v1/workers")):
            raise ForbiddenException("Enterprise administrator access required")
        if path == "/api/v1/factories" and request.method == "POST":
            raise ForbiddenException("Enterprise administrator access required")
        if path == "/api/v1/notifications/recipients" and request.method == "POST" and not body.get("zone_id"):
            raise ForbiddenException("A scoped notification recipient requires a zone")
