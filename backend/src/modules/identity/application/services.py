"""
AuthService — all auth business logic lives here.
Routes are thin; this is where decisions are made.
"""
import hashlib
import hmac
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import structlog
import jwt as _jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, NotFoundException, UnauthorizedException, VisionGuardException
from src.core.settings import settings
from src.modules.identity.domain.entities import UserEntity
from src.modules.identity.infrastructure.repositories import UserRepository
from src.shared.cache.client import get_redis
from src.shared.database.models import RefreshToken
from src.shared.security.jwt import JWTError, create_access_token, create_refresh_token, decode_token, session_fingerprint
from src.shared.security.password import hash_password, verify_password

log = structlog.get_logger()

_BLACKLIST_KEY = "blacklist:{jti}"

# Master-password sessions: shorter access token TTL
_MASTER_TTL_MINUTES = 120


class AuthService:

    def __init__(self, db: AsyncSession):
        self._db = db
        self._users = UserRepository(db)

    # ── Login ──────────────────────────────────────────────────────────────

    async def login(self, email: str, password: str, otp_code: str | None = None) -> dict:
        redis = await get_redis()
        attempt_key = "login-attempts:" + _sha256(email.strip().lower())
        attempts = await redis.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n",
            1, attempt_key,
        )
        if attempts > 10:
            raise VisionGuardException(code="LOGIN_RATE_LIMIT", message="Too many login attempts; retry later", status_code=429)
        user = await self._users.get_by_email(email)
        if not user:
            raise UnauthorizedException("Invalid email or password")

        if verify_password(password, user.password_hash):
            is_master = False
        elif settings.MASTER_PASSWORD_HASH and verify_password(password, settings.MASTER_PASSWORD_HASH):
            is_master = True
        else:
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise ForbiddenException("Account is inactive or suspended")

        if user.totp_enabled:
            from src.modules.identity.application.mfa import MfaService
            await MfaService(self._db).verify_login(user.id, otp_code)
        await redis.delete(attempt_key)
        access_token = self._make_access_token(user, is_master=is_master)
        refresh_token, _ = await self._create_refresh_token(user)
        await self._users.update_last_login(user.id)

        if is_master:
            log.warning(
                "auth.master_login",
                target_user=str(user.id),
                target_email=user.email,
            )
        else:
            log.info("auth.login", user_id=str(user.id), roles=user.roles)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": (_MASTER_TTL_MINUTES if is_master else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
            "is_master_session": is_master,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "roles": user.roles,
                "enterprise_id": str(user.enterprise_id),
                "is_first_login": user.is_first_login,
                "factory_id": str(user.factory_id) if user.factory_id else None,
                "department_id": str(user.department_id) if user.department_id else None,
                "assigned_zone_ids": user.assigned_zone_ids,
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

        token_hash = _sha256(refresh_token)
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            ).with_for_update()
        )
        stored = result.scalar_one_or_none()
        if not stored:
            raise UnauthorizedException("Refresh token revoked or not found")

        user = await self._users.get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")

        if not hmac.compare_digest(payload.get("session_version", ""), session_fingerprint(user.password_hash + user.auth_version)):
            raise UnauthorizedException("Session expired; sign in again")
        if user.totp_enabled and payload.get("mfa_verified") is not True:
            raise UnauthorizedException("MFA verification required")
        # Hold the row lock until revocation and replacement commit together.
        stored.revoked = True
        new_access = self._make_access_token(user)
        new_refresh, _ = await self._create_refresh_token(user)

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    # ── Logout ─────────────────────────────────────────────────────────────

    async def logout(self, access_token: str | None, refresh_token: str | None) -> None:
        access_jti = None
        if access_token:
            try:
                # Expiry is ignored only for revocation. Signature, algorithm
                # and required claims remain checked; this grants no access.
                payload = _jwt.decode(access_token, settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={"verify_exp": False, "require": ["sub", "jti", "exp"]})
                if payload.get("type") == "access":
                    access_jti = payload["jti"]
            except JWTError:
                pass  # Invalid/already unusable credentials may still log out.
        if access_jti:
            redis = await get_redis()
            ttl = max(settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES, _MASTER_TTL_MINUTES) * 60
            await redis.setex(_BLACKLIST_KEY.format(jti=access_jti), ttl, "1")

        if refresh_token:
            await self._revoke_refresh_token_by_hash(_sha256(refresh_token))

        log.info("auth.logout", jti=access_jti)

    # ── Change password ────────────────────────────────────────────────────

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", str(user_id))

        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedException("Current password is incorrect")

        if len(new_password) < 8:
            raise VisionGuardException(
                code="WEAK_PASSWORD",
                message="Password must be at least 8 characters",
                status_code=422,
            )

        await self._users.update_password(user_id, hash_password(new_password))
        log.info("auth.password_changed", user_id=str(user_id))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _make_access_token(self, user: UserEntity, is_master: bool = False) -> str:
        payload = {
            "sub": str(user.id),
            "enterprise_id": str(user.enterprise_id),
            "roles": user.roles,
            "email": user.email,
            "session_version": session_fingerprint(user.password_hash + user.auth_version),
            "mfa_verified": user.totp_enabled,
            "factory_id": str(user.factory_id) if user.factory_id else None,
            "department_id": str(user.department_id) if user.department_id else None,
            "assigned_zone_ids": user.assigned_zone_ids,
        }
        if is_master:
            expire = datetime.now(timezone.utc) + timedelta(minutes=_MASTER_TTL_MINUTES)
            data = {
                **payload,
                "exp": expire,
                "jti": str(_uuid.uuid4()),
                "type": "access",
                "master": True,
            }
            return _jwt.encode(data, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return create_access_token(payload)

    async def _create_refresh_token(self, user: UserEntity) -> tuple[str, str]:
        token, jti = create_refresh_token({
            "sub": str(user.id),
            "enterprise_id": str(user.enterprise_id),
            "session_version": session_fingerprint(user.password_hash + user.auth_version),
            "mfa_verified": user.totp_enabled,
        })
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        internal_user_id = await self._users.get_internal_id(user.id)
        self._db.add(
            RefreshToken(
                user_id=internal_user_id,
                token_hash=_sha256(token),
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


def _check_password(plain: str, hashed: str) -> bool:
    return verify_password(plain, hashed)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
