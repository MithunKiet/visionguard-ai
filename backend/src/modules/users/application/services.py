"""
UserManagementService — invite/list/update/deactivate users within an
enterprise. Distinct from identity.application.services.AuthService, which
owns login/tokens; this owns account administration.

Permission model (who can assign which roles to a new/existing user):
  SYSTEM_ADMIN      -> any role, including SYSTEM_ADMIN/ENTERPRISE_ADMIN
  ENTERPRISE_ADMIN  -> FACTORY_MANAGER / SAFETY_OFFICER / SUPERVISOR / VIEWER
  FACTORY_MANAGER   -> SAFETY_OFFICER / SUPERVISOR / VIEWER, and only for
                       their own factory (factory_id is forced to the
                       caller's own, never taken from the request)
A caller holding multiple roles gets the union of what each grants — same
philosophy as shared/security/scope.py's get_scope(). Both endpoints and
this service scope every operation to the caller's own enterprise; a
SYSTEM_ADMIN managing a different enterprise's users is out of scope for
this module (enterprise-onboarding already covers creating a new tenant's
first admin — see modules/enterprise).
"""
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, NotFoundException, VisionGuardException
from src.modules.users.domain.entities import UserAdminEntity
from src.modules.users.infrastructure.repositories import UserAdminRepository
from src.shared.email.sender import send_email
from src.shared.security.password import generate_temp_password, hash_password
from src.shared.security.scope import ScopeFilter

log = structlog.get_logger()

_ASSIGNABLE_ROLES = {
    "SYSTEM_ADMIN": {"SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER", "SUPERVISOR", "VIEWER"},
    "ENTERPRISE_ADMIN": {"FACTORY_MANAGER", "SAFETY_OFFICER", "SUPERVISOR", "VIEWER"},
    "FACTORY_MANAGER": {"SAFETY_OFFICER", "SUPERVISOR", "VIEWER"},
}
_FACTORY_LOCKED_ROLES = {"FACTORY_MANAGER"}  # roles that must scope factory_id to the caller's own


class UserManagementService:

    def __init__(self, repo: UserAdminRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    @staticmethod
    def _assignable_roles(caller_roles: list[str]) -> set[str]:
        allowed: set[str] = set()
        for r in caller_roles:
            allowed |= _ASSIGNABLE_ROLES.get(r, set())
        return allowed

    def _validate_roles(self, caller_roles: list[str], requested_roles: list[str]) -> None:
        if not requested_roles:
            raise VisionGuardException(
                code="ROLE_REQUIRED", message="At least one role is required", status_code=422,
            )
        allowed = self._assignable_roles(caller_roles)
        disallowed = set(requested_roles) - allowed
        if disallowed:
            raise ForbiddenException(
                f"You aren't permitted to assign: {', '.join(sorted(disallowed))}"
            )

    async def list_users(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[dict]:
        users = await self._repo.list(enterprise_id, scope)
        return [self.to_dict(u) for u in users]

    async def get_user(
        self, user_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> dict:
        user = await self._repo.get_by_id(user_id, enterprise_id, scope)
        if not user:
            raise NotFoundException("User", str(user_id))
        return self.to_dict(user)

    async def invite_user(
        self,
        enterprise_id: str,
        invited_by: str,
        caller_roles: list[str],
        caller_factory_id: str | None,
        name: str,
        email: str,
        roles: list[str],
        factory_id: str | None = None,
        department_id: str | None = None,
        assigned_zone_ids: list[str] | None = None,
    ) -> dict:
        self._validate_roles(caller_roles, roles)

        # A FACTORY_MANAGER can only invite people into their own factory —
        # override rather than trust whatever factory_id the request sent.
        if _FACTORY_LOCKED_ROLES & set(caller_roles) and not ({"SYSTEM_ADMIN", "ENTERPRISE_ADMIN"} & set(caller_roles)):
            factory_id = caller_factory_id

        if await self._repo.email_exists(email):
            raise VisionGuardException(
                code="EMAIL_ALREADY_REGISTERED",
                message=f"'{email}' is already registered to another account",
                status_code=409,
            )

        temp_password = generate_temp_password()
        entity = UserAdminEntity(
            enterprise_id=enterprise_id,
            name=name,
            email=email,
            roles=roles,
            factory_id=factory_id,
            department_id=department_id,
            assigned_zone_ids=assigned_zone_ids or [],
        )
        created = await self._repo.create(entity, hash_password(temp_password), invited_by)

        email_sent = await send_email(
            to=email,
            subject="You've been added to VisionGuard AI",
            body_html=(
                f"<p>Hi {name},</p>"
                f"<p>You've been added to VisionGuard AI with the role(s): <b>{', '.join(roles)}</b>.</p>"
                f"<p>Email: {email}<br>Temporary password: <b>{temp_password}</b></p>"
                f"<p>You'll be asked to set a new password on first login.</p>"
            ),
        )
        log.info("user.invited", user_id=str(created.id), email=email, roles=roles,
                 welcome_email_sent=email_sent)

        return {
            **self.to_dict(created),
            # Only ever returned once, from this call — see EnterpriseService
            # for the same pattern and why (no SMTP configured in dev = this
            # is the only place to retrieve it).
            "temp_password": temp_password,
            "welcome_email_sent": email_sent,
        }

    async def update_user(
        self,
        user_id: str,
        enterprise_id: str,
        caller_roles: list[str],
        caller_factory_id: str | None,
        scope: ScopeFilter | None,
        **fields,
    ) -> dict:
        existing = await self._repo.get_by_id(user_id, enterprise_id, scope)
        if not existing:
            raise NotFoundException("User", str(user_id))

        role_codes = fields.pop("roles", None)
        if role_codes is not None:
            self._validate_roles(caller_roles, role_codes)

        if "factory_id" in fields and _FACTORY_LOCKED_ROLES & set(caller_roles) \
                and not ({"SYSTEM_ADMIN", "ENTERPRISE_ADMIN"} & set(caller_roles)):
            fields["factory_id"] = caller_factory_id

        fields = {k: v for k, v in fields.items() if v is not None}
        updated = await self._repo.update(user_id, enterprise_id, fields, role_codes)
        log.info("user.updated", user_id=str(user_id), fields=list(fields.keys()))
        return self.to_dict(updated)

    async def deactivate_user(
        self, user_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> None:
        existing = await self._repo.get_by_id(user_id, enterprise_id, scope)
        if not existing:
            raise NotFoundException("User", str(user_id))
        await self._repo.deactivate(user_id, enterprise_id)
        log.info("user.deactivated", user_id=str(user_id))

    @staticmethod
    def to_dict(u: UserAdminEntity) -> dict:
        return {
            "id": u.id,
            "enterprise_id": u.enterprise_id,
            "name": u.name,
            "email": u.email,
            "status": u.status,
            "roles": u.roles,
            "factory_id": u.factory_id,
            "factory_name": u.factory_name,
            "department_id": u.department_id,
            "department_name": u.department_name,
            "assigned_zone_ids": u.assigned_zone_ids,
            "is_first_login": u.is_first_login,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
