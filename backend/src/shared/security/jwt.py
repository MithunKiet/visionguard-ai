import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from src.core.settings import settings

_ALGORITHM = settings.JWT_ALGORITHM
_SECRET = settings.JWT_SECRET


def create_access_token(payload: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    data = {**payload, "exp": expire, "jti": str(uuid.uuid4()), "type": "access"}
    return jwt.encode(data, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(payload: dict[str, Any]) -> tuple[str, str]:
    """Returns (encoded_token, jti)."""
    jti = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    data = {**payload, "exp": expire, "jti": jti, "type": "refresh"}
    return jwt.encode(data, _SECRET, algorithm=_ALGORITHM), jti


def decode_token(token: str) -> dict[str, Any]:
    """Raises JWTError on invalid / expired token."""
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])


__all__ = ["create_access_token", "create_refresh_token", "decode_token", "JWTError"]
