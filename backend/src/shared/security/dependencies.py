"""FastAPI dependencies for auth, RBAC, and tenant context."""
from uuid import UUID

import hmac

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.session import get_db
from src.shared.security.jwt import JWTError

from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.settings import settings
from src.shared.security.jwt import decode_token


class AuthUser:
    def __init__(self, payload: dict):
        self.user_id: str = payload["sub"]
        self.enterprise_id: str = payload["enterprise_id"]
        self.roles: list[str] = payload.get("roles", [])
        self.jti: str = payload["jti"]
        self.email: str = payload.get("email", "")
        self.factory_id: str | None = payload.get("factory_id")
        self.department_id: str | None = payload.get("department_id")
        self.assigned_zone_ids: list[str] = payload.get("assigned_zone_ids") or []


async def authenticate_token(token: str, db: AsyncSession) -> AuthUser:
    from src.modules.identity.infrastructure.repositories import UserRepository
    from src.shared.cache.client import get_redis
    from src.shared.security.jwt import session_fingerprint

    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or not payload.get("sub") or not payload.get("jti"):
            raise JWTError("Invalid access claims")
    except JWTError:
        raise UnauthorizedException("Invalid or expired access token")
    redis = await get_redis()
    if await redis.exists(f"blacklist:{payload['jti']}"):
        raise UnauthorizedException("Session revoked")
    current = await UserRepository(db).get_by_id(payload["sub"])
    if not current or not current.is_active or current.totp_enabled:
        raise UnauthorizedException("User not found or inactive")
    if not hmac.compare_digest(payload.get("session_version", ""), session_fingerprint(current.password_hash)):
        raise UnauthorizedException("Session expired; sign in again")
    if payload.get("enterprise_id") != current.enterprise_id:
        raise UnauthorizedException("Session tenant changed")
    # Authorization always uses the current account, never stale JWT permissions.
    payload.update(roles=current.roles, factory_id=current.factory_id,
                   department_id=current.department_id, assigned_zone_ids=current.assigned_zone_ids,
                   email=current.email, name=current.name, is_first_login=current.is_first_login)
    user = AuthUser(payload)
    user.name = current.name
    user.is_first_login = current.is_first_login
    db.info["enterprise_id"] = current.enterprise_id
    return user


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    user = await authenticate_token(_extract_bearer(authorization), db)
    if user.is_first_login and request.url.path not in {
        "/api/v1/auth/me", "/api/v1/auth/change-password", "/api/v1/auth/logout",
    }:
        raise ForbiddenException("Change your temporary password before continuing")
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    async def _check(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not allowed & set(user.roles):
            raise ForbiddenException(
                f"Role(s) {user.roles} not permitted. Required one of: {list(roles)}"
            )
        return user

    return _check


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Missing or malformed Authorization header")
    return authorization[7:]


class WorkerContext:
    """Identity for an AI Worker calling backend service endpoints (no user JWT)."""
    def __init__(self, enterprise_id: str, worker_id: str | None = None):
        self.enterprise_id = enterprise_id
        self.worker_id = worker_id


async def get_worker_context(
    x_worker_key: str | None = Header(default=None),
    x_enterprise_id: str | None = Header(default=None),
) -> WorkerContext:
    if settings.WORKER_CREDENTIALS:
        for worker_id, credential in settings.WORKER_CREDENTIALS.items():
            if x_worker_key and hmac.compare_digest(x_worker_key, credential.get("key", "")):
                if not x_enterprise_id or x_enterprise_id != credential.get("enterprise_id"):
                    raise UnauthorizedException("Worker tenant mismatch")
                return WorkerContext(x_enterprise_id, worker_id)
        raise UnauthorizedException("Invalid worker credentials")
    if not x_worker_key or not hmac.compare_digest(x_worker_key, settings.WORKER_API_KEY):
        raise UnauthorizedException("Invalid or missing worker API key")
    if not x_enterprise_id:
        raise UnauthorizedException("Missing X-Enterprise-Id header")
    try:
        UUID(x_enterprise_id)
    except ValueError:
        raise UnauthorizedException("X-Enterprise-Id must be a valid UUID")
    return WorkerContext(enterprise_id=x_enterprise_id)
