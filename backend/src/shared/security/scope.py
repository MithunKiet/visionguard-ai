"""
Data-visibility scoping — which factory/zone rows a user is allowed to
see, derived from their role(s) plus their stored factory_id/
department_id/assigned_zone_ids (both carried on AuthUser, from the JWT —
see shared/security/dependencies.py).

This is a different concern from require_roles(): that gates WHETHER an
endpoint can be called at all; this gates WHICH ROWS within an endpoint
the caller can see. A FACTORY_MANAGER passes require_roles() on the zones
endpoint same as an ENTERPRISE_ADMIN would, but should only see their own
factory's zones — that's what apply_scope() enforces at the query level.
"""
from dataclasses import dataclass, field

from sqlalchemy import false, or_

from src.shared.security.dependencies import AuthUser

# Roles that see everything in their enterprise — no factory/zone restriction.
_UNRESTRICTED_ROLES = {"SYSTEM_ADMIN", "ENTERPRISE_ADMIN"}
# Roles restricted to their own factory.
_FACTORY_SCOPED_ROLES = {"FACTORY_MANAGER", "SAFETY_OFFICER"}
# Roles restricted to their explicitly assigned zones (falling back to
# factory-wide if no specific zones were assigned).
_ZONE_SCOPED_ROLES = {"SUPERVISOR", "VIEWER"}


@dataclass
class ScopeFilter:
    unrestricted: bool
    factory_ids: set[str] = field(default_factory=set)
    zone_ids: set[str] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        """True if this user's roles grant no visible rows at all (e.g. a
        role with no matching factory_id/assigned_zone_ids set) — callers
        should return zero rows rather than skip filtering in this case."""
        return not self.unrestricted and not self.factory_ids and not self.zone_ids


def get_scope(user: AuthUser) -> ScopeFilter:
    """A user's overall scope is the union of what each of their roles
    grants — holding even one unrestricted role (e.g. ENTERPRISE_ADMIN)
    makes the whole user unrestricted, even if they also hold a narrower
    role like SUPERVISOR."""
    roles = set(user.roles)

    if roles & _UNRESTRICTED_ROLES:
        return ScopeFilter(unrestricted=True)

    factory_ids: set[str] = set()
    zone_ids: set[str] = set()

    if roles & _FACTORY_SCOPED_ROLES and user.factory_id:
        factory_ids.add(user.factory_id)

    if roles & _ZONE_SCOPED_ROLES:
        if user.assigned_zone_ids:
            zone_ids.update(user.assigned_zone_ids)
        elif user.factory_id:
            factory_ids.add(user.factory_id)

    return ScopeFilter(unrestricted=False, factory_ids=factory_ids, zone_ids=zone_ids)


async def apply_zone_scope(db, query, scope: ScopeFilter, factory_id_col, zone_id_col):
    """Restrict a query selecting factory/zone-bearing rows (zones,
    cameras, alerts, ...) to what `scope` allows. `factory_id_col` and
    `zone_id_col` are the SQLAlchemy columns to filter on for that model.

    `scope.factory_ids`/`scope.zone_ids` are public_id strings (from the
    JWT); `factory_id_col`/`zone_id_col` are internal-integer FK columns, so
    this resolves one side to match the other before filtering."""
    if scope.unrestricted:
        return query
    if scope.is_empty:
        return query.where(false())

    from src.shared.database.models import Factory, Zone
    from src.shared.database.pid import to_pks

    conditions = []
    if scope.factory_ids:
        pks = await to_pks(db, Factory, list(scope.factory_ids))
        if pks:
            conditions.append(factory_id_col.in_(pks))
    if scope.zone_ids:
        pks = await to_pks(db, Zone, list(scope.zone_ids))
        if pks:
            conditions.append(zone_id_col.in_(pks))
    if not conditions:
        return query.where(false())
    return query.where(or_(*conditions))


async def apply_factory_scope(db, query, scope: ScopeFilter, factory_id_col):
    """Restrict a query over factory-level rows (Factory itself, or anything
    else keyed directly by factory with no zone_id of its own — e.g.
    Department) to what `scope` allows.

    Zone-scoped roles (SUPERVISOR/VIEWER with specific assigned zones) carry
    their visibility in scope.zone_ids, not scope.factory_ids — but they
    still need to see their own factory/department for context/navigation,
    so their visible factory set here is derived from their assigned zones'
    parent factory."""
    if scope.unrestricted:
        return query
    if scope.is_empty:
        return query.where(false())

    from sqlalchemy import select
    from src.shared.database.models import Factory, Zone
    from src.shared.database.pid import to_pks

    factory_pks: set[int] = set()
    if scope.factory_ids:
        factory_pks.update(await to_pks(db, Factory, list(scope.factory_ids)))
    if scope.zone_ids:
        zone_pks = await to_pks(db, Zone, list(scope.zone_ids))
        if zone_pks:
            rows = await db.execute(select(Zone.factory_id).where(Zone.id.in_(zone_pks)))
            factory_pks.update(r[0] for r in rows.all())

    if not factory_pks:
        return query.where(false())
    return query.where(factory_id_col.in_(factory_pks))
