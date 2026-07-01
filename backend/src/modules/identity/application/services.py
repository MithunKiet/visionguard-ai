"""
AuthService — all auth business logic lives here.
Routes are thin; this is where decisions are made.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, NotFoundException, UnauthorizedException
from src.core.settings import settings
from src.modules.identity.domain.entities import UserEntity
from src.modules.identity.infrastructure.repositories import UserRepository
from src.shared.cache.client import get_redis
from src.shared.database.models import RefreshToken
from src.shared.security.jwt import JWTError, create_access_token, create_refresh_token, decode_token
from src.shared.security.password import hash_password, verify_password

log = structlog.get_logger()

_REFRESH_KEY = "rt:{jti}"          # Redis key for fast revocation lookup
_BLACKLIST_KEY = "blacklist:{jti}"  # Blacklisted access token JTIs


class AuthService:

    def __init__(self, db: AsyncSession):
        self._db = db
        self._users = UserRepository(db)

    # ── Login ──────────────────────────────────────────────────────────────

    async def login(self, email: str, password: str) -> dict:
        user = await self._users.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise ForbiddenException("Account is inactive or suspended")

        access_token = self._make_access_token(user)
        refresh_token, jti = await self._create_refresh_token(user)

        await self._users.update_last_login(user.id)

        log.info("auth.login", user_id=str(user.id), role=user.role)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "enterprise_id": str(user.enterprise_id),
                "is_first_login": user.is_first_login,
            },
        }

    # ── Refresh ────────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise UnauthorizedException("Invalid or expired refresh token")

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Not a refresh token")

        jti = payload["jti"]
        token_hash = _sha256(refresh_token)

        # Verify token exists in DB and is not revoked
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
            )
        )
        stored = result.scalar_one_or_none()
        if not stored:
            raise UnauthorizedException("Refresh token revoked or not found")

        user = await self._users.get_by_id(UUID(payload["sub"]))
        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")

        # Rotate: revoke old, issue new
        await self._revoke_refresh_token_by_hash(token_hash)
        new_access = self._make_access_token(user)
        new_refresh, _ = await self._create_refresh_token(user)

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    # ── Logout ─────────────────────────────────────────────────────────────

    async def logout(self, access_jti: str, refresh_token: str | None) -> None:
        # Blacklist current access token JTI in Redis until its natural expiry
        redis = await get_redis()
        ttl = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        await redis.setex(_BLACKLIST_KEY.format(jti=access_jti), ttl, "1")

        if refresh_token:
            token_hash = _sha256(refresh_token)
            await self._revoke_refresh_token_by_hash(token_hash)

        log.info("auth.logout", jti=access_jti)

    # ── Change password ────────────────────────────────────────────────────

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", str(user_id))

        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedException("Current password is incorrect")

        if len(new_password) < 8:
            from src.core.exceptions import VisionGuardException
            raise VisionGuardException(
                code="WEAK_PASSWORD",
                message="Password must be at least 8 characters",
                status_code=422,
            )

        await self._users.update_password(user_id, hash_password(new_password))
        log.info("auth.password_changed", user_id=str(user_id))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _make_access_token(self, user: UserEntity) -> str:
        return create_access_token({
            "sub": str(user.id),
            "enterprise_id": str(user.enterprise_id),
            "role": user.role,
            "email": user.email,
        })

    async def _create_refresh_token(self, user: UserEntity) -> tuple[str, str]:
        token, jti = create_refresh_token({
            "sub": str(user.id),
            "enterprise_id": str(user.enterprise_id),
        })
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        token_hash = _sha256(token)
        self._db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await self._db.commit()
        return token, jti

    async def _revoke_refresh_token_by_hash(self, token_hash: str) -> None:
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )
        await self._db.commit()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
