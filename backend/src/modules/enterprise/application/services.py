"""
EnterpriseService — dynamic branding (master context rules #1, #2): all
company names, logos, and colors live in the enterprises table and are
served from here at runtime. Nothing is hardcoded anywhere in the platform.

Also owns platform-level enterprise onboarding (SYSTEM_ADMIN only) — creating
a new client tenant plus its first ENTERPRISE_ADMIN user, per the documented
onboarding flow (AI_MASTER_CONTEXT Section 14).
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, VisionGuardException
from src.shared.database.models import Enterprise, Role, User, UserRole
from src.shared.database.pid import to_pk
from src.shared.email.sender import send_email
from src.shared.security.password import generate_temp_password, hash_password

log = structlog.get_logger()

_BRANDING_FIELDS = ("name", "tagline", "primary_color", "secondary_color", "logo_url", "favicon_url")


class EnterpriseService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_branding(self, enterprise_id: str) -> dict:
        return self.to_branding(await self._get_row(enterprise_id))

    async def update_branding(self, enterprise_id: str, changes: dict) -> dict:
        row = await self._get_row(enterprise_id)
        for field in _BRANDING_FIELDS:
            if changes.get(field) is not None:
                setattr(row, field, changes[field])
        await self._db.commit()
        await self._db.refresh(row)
        log.info("enterprise.branding_updated", enterprise_id=str(enterprise_id))
        return self.to_branding(row)

    async def _get_row(self, enterprise_id: str) -> Enterprise:
        row = (await self._db.execute(
            select(Enterprise).where(Enterprise.public_id == enterprise_id)
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("Enterprise", str(enterprise_id))
        return row

    @staticmethod
    def to_branding(e: Enterprise) -> dict:
        return {
            "id": e.public_id,
            "name": e.name,
            "code": e.code,
            "tagline": e.tagline,
            "logo_url": e.logo_url,
            "favicon_url": e.favicon_url,
            "primary_color": e.primary_color,
            "secondary_color": e.secondary_color,
        }

    # ── Platform-level onboarding (SYSTEM_ADMIN only) ────────────────────────

    async def list_enterprises(self) -> list[dict]:
        """Cross-tenant listing — legitimate only for SYSTEM_ADMIN, enforced
        at the route level, not here (this service has no enterprise_id
        scoping to begin with, matching the platform-wide nature of the call)."""
        rows = (await self._db.execute(select(Enterprise).order_by(Enterprise.name))).scalars()
        return [self.to_full_dict(r) for r in rows]

    async def create_enterprise(
        self,
        name: str,
        code: str,
        admin_name: str,
        admin_email: str,
        created_by: str,
        industry: str | None = None,
        contact_person: str | None = None,
        contact_email: str | None = None,
        primary_color: str | None = None,
        secondary_color: str | None = None,
    ) -> dict:
        existing = (await self._db.execute(
            select(Enterprise).where(Enterprise.code == code)
        )).scalar_one_or_none()
        if existing:
            raise VisionGuardException(
                code="ENTERPRISE_CODE_TAKEN",
                message=f"Enterprise code '{code}' is already in use",
                status_code=409,
            )
        existing_admin = (await self._db.execute(
            select(User).where(User.email == admin_email)
        )).scalar_one_or_none()
        if existing_admin:
            raise VisionGuardException(
                code="EMAIL_ALREADY_REGISTERED",
                message=f"'{admin_email}' is already registered to another account",
                status_code=409,
            )

        enterprise = Enterprise(
            name=name, code=code, status="Active",
            industry=industry, contact_person=contact_person, contact_email=contact_email,
            primary_color=primary_color or "#1565C0", secondary_color=secondary_color or "#42A5F5",
        )
        self._db.add(enterprise)
        await self._db.flush()

        temp_password = generate_temp_password()
        invited_by_pk = await to_pk(self._db, User, created_by)
        admin = User(
            enterprise_id=enterprise.id, name=admin_name, email=admin_email,
            password_hash=hash_password(temp_password), status="Active",
            is_first_login=True, setup_completed=False,
            invited_by=invited_by_pk, invited_at=datetime.now(timezone.utc),
        )
        self._db.add(admin)
        await self._db.flush()
        admin_role = (await self._db.execute(
            select(Role).where(Role.code == "ENTERPRISE_ADMIN")
        )).scalar_one()
        self._db.add(UserRole(user_public_id=admin.public_id, role_public_id=admin_role.public_id))
        await self._db.commit()
        await self._db.refresh(enterprise)

        email_sent = await send_email(
            to=admin_email,
            subject=f"Welcome to VisionGuard AI — {name}",
            body_html=(
                f"<p>Hi {admin_name},</p>"
                f"<p>Your VisionGuard AI account for <b>{name}</b> has been created.</p>"
                f"<p>Email: {admin_email}<br>Temporary password: <b>{temp_password}</b></p>"
                f"<p>You'll be asked to set a new password on first login, then walked "
                f"through the setup wizard.</p>"
            ),
        )
        log.info("enterprise.created", enterprise_id=str(enterprise.id), code=code,
                 admin_email=admin_email, welcome_email_sent=email_sent)

        return {
            **self.to_full_dict(enterprise),
            "admin_email": admin_email,
            # Only ever returned once, from this call — not retrievable again.
            # If welcome_email_sent is False (no SMTP configured in this
            # environment), this is the only place to see it.
            "temp_password": temp_password,
            "welcome_email_sent": email_sent,
        }

    @staticmethod
    def to_full_dict(e: Enterprise) -> dict:
        return {
            "id": e.public_id,
            "name": e.name,
            "code": e.code,
            "tagline": e.tagline,
            "logo_url": e.logo_url,
            "favicon_url": e.favicon_url,
            "primary_color": e.primary_color,
            "secondary_color": e.secondary_color,
            "industry": e.industry,
            "contact_person": e.contact_person,
            "contact_email": e.contact_email,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
