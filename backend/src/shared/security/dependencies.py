"""
FastAPI dependencies for auth, RBAC, and tenant context.

Usage:
    from src.shared.security.dependencies import get_current_user, require_roles, AuthUser

    @router.get("/...")
    async def endpoint(user: AuthUser = Depends(get_current_user)):
        ...

    # Role-gated:
    @router.get("/admin")
    async def admin_endpoint(user: AuthUser = Depends(require_roles("SUPER_ADMIN", "HO_ADMIN"))):
        ...
"""
from uuid import UUID

from fastapi import Depends, Header
from jose import JWTError

from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.settings import settings
from src.shared.security.jwt import decode_token


class AuthUser:
    def __init__(self, payload: dict):
        self.user_id: str       = payload["sub"]
        self.enterprise_id: str = payload["enterprise_id"]
        self.role: str          = payload["role"]
        self.jti: str           = payload["jti"]
        self.email: str         = payload.get("email", "")


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> AuthUser:
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedException("Invalid or expired access token")

    if payload.get("type") != "access":
        raise UnauthorizedException("Not an access token")

    return AuthUser(payload)


def require_roles(*roles: str):
    """Dependency factory — gates an endpoint to users with specific roles."""
    async def _check(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in roles:
            raise ForbiddenException(
                f"Role '{user.role}' is not permitted. Required one of: {list(roles)}"
            )
        return user
    return _check


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Missing or malformed Authorization header")
    return authorization[7:]


class WorkerContext:
    """Identity for an AI Worker calling backend service endpoints (no user JWT)."""
    def __init__(self, enterprise_id: str):
        self.enterprise_id = enterprise_id


async def get_worker_context(
    x_worker_key: str | None = Header(default=None),
    x_enterprise_id: str | None = Header(default=None),
) -> WorkerContext:
    if not x_worker_key or x_worker_key != settings.WORKER_API_KEY:
        raise UnauthorizedException("Invalid or missing worker API key")
    if not x_enterprise_id:
        raise UnauthorizedException("Missing X-Enterprise-Id header")
    try:
        UUID(x_enterprise_id)
    except ValueError:
        raise UnauthorizedException("X-Enterprise-Id must be a valid UUID")
    return WorkerContext(enterprise_id=x_enterprise_id)
