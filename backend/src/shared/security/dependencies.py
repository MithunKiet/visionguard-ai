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
from fastapi import Depends, Header
from jose import JWTError

from src.core.exceptions import ForbiddenException, UnauthorizedException
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
