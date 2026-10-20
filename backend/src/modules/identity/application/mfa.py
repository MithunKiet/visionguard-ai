"""Password-confirmed TOTP enrollment, replay protection and atomic security audit."""
import base64
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from src.core.exceptions import UnauthorizedException, VisionGuardException
from src.core.settings import settings
from src.shared.cache.client import get_redis
from src.shared.database.models import AuditLog, User
from src.shared.security.password import verify_password


def cipher():
    # Purpose-separated encryption key; JWT secret rotation requires re-enrollment.
    key = hashlib.sha256(b"visionguard-totp-v1:" + settings.JWT_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class MfaService:
    def __init__(self, db):
        self.db = db

    async def throttle(self, user_id):
        redis = await get_redis()
        attempts = await redis.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n",
            1, "mfa-attempts:" + str(user_id),
        )
        if attempts > 10:
            raise VisionGuardException(code="MFA_RATE_LIMIT", message="Too many MFA attempts; retry later", status_code=429)

    async def row(self, user_id):
        row = await self.db.scalar(select(User).where(User.public_id == user_id, User.deleted_at.is_(None)).with_for_update())
        if not row or row.status != "Active":
            raise UnauthorizedException("Account unavailable")
        return row

    def verify(self, row, encrypted, code):
        try:
            secret = cipher().decrypt(encrypted.encode()).decode()
        except (InvalidToken, AttributeError):
            raise UnauthorizedException("MFA unavailable; contact your administrator")
        step = int(time.time()) // 30
        # Allow clock skew of one step; each accepted step can only be used once.
        matched = next((n for n in [step - 1, step, step + 1]
                        if code and hmac.compare_digest(pyotp.TOTP(secret).at(n * 30), code)), None)
        if matched is None or (row.totp_last_step is not None and matched <= row.totp_last_step):
            raise UnauthorizedException("Invalid or already used authenticator code")
        row.totp_last_step = matched

    async def verify_login(self, user_id, code):
        await self.throttle(user_id)
        row = await self.row(user_id)
        if not row.totp_enabled:
            raise UnauthorizedException("Account security changed; sign in again")
        self.verify(row, row.totp_secret, code)
        await self.db.commit()

    async def manage(self, user_id, password, code, operation):
        await self.throttle(user_id)
        row = await self.row(user_id)
        if not verify_password(password, row.password_hash):
            raise UnauthorizedException("Current password is incorrect")
        now = datetime.now(timezone.utc)
        result = None
        if operation == "setup":
            if row.totp_enabled:
                raise UnauthorizedException("MFA already enabled")
            secret = pyotp.random_base32()
            row.totp_pending_secret = cipher().encrypt(secret.encode()).decode()
            row.totp_pending_until = now + timedelta(minutes=10)
            result = {"secret": secret, "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(row.email, issuer_name="VisionGuard AI"), "expires_in": 600}
        elif operation == "enable":
            if row.totp_enabled or not row.totp_pending_until or row.totp_pending_until <= now:
                raise UnauthorizedException("Start a new authenticator setup")
            self.verify(row, row.totp_pending_secret, code)
            row.totp_secret = row.totp_pending_secret
            row.totp_enabled = True
        elif operation == "disable":
            if not row.totp_enabled:
                raise UnauthorizedException("MFA is not enabled")
            self.verify(row, row.totp_secret, code)
            row.totp_enabled = False
            row.totp_secret = None
            row.totp_last_step = None
        else:
            raise ValueError("Unknown MFA operation")
        if operation != "setup":
            row.auth_version = str(uuid4())
            row.totp_pending_secret = None
            row.totp_pending_until = None
        self.db.add(AuditLog(enterprise_id=row.enterprise_id, user_id=row.id,
                            action="MFA_" + operation.upper(), entity_type="user", entity_id=row.public_id))
        await self.db.commit()
        return result
