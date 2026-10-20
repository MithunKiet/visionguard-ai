# ruff: noqa: F811
"""MFA acceptance against disposable PostgreSQL and Redis."""
import time
import os
from types import SimpleNamespace
from unittest.mock import patch

import pyotp
import pytest
from sqlalchemy import select, text

from tests.test_review_integration import setup, headers  # noqa: F401
from src.modules.identity.application.mfa import cipher
from src.shared.database.models import AuditLog, User
from src.shared.database.session import AsyncSessionFactory

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


@pytest.mark.asyncio
async def test_mfa_lifecycle(setup):
    s = setup
    credentials = {'email': s.users['admin'].email, 'password': 'Test-password-391'}
    login = await s.client.post('/api/v1/auth/login', json=credentials)
    old_refresh = login.json()['data']['refresh_token']
    response = await s.client.post('/api/v1/auth/mfa/setup', headers=headers(s), json={'password': 'Test-password-391'})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    secret = response.json()['data']['secret']
    async with AsyncSessionFactory() as db:
        row = await db.scalar(select(User).where(User.id == s.users['admin'].id))
        assert row.totp_pending_secret != secret
        assert cipher().decrypt(row.totp_pending_secret.encode()).decode() == secret
        assert not row.totp_enabled
    response = await s.client.post('/api/v1/auth/mfa/enable', headers=headers(s), json={
        'password': 'Test-password-391', 'otp_code': pyotp.TOTP(secret).now()})
    assert response.status_code == 200, response.text
    assert (await s.client.get('/api/v1/auth/me', headers=headers(s))).status_code == 401
    assert (await s.client.post('/api/v1/auth/refresh', json={'refresh_token': old_refresh})).status_code == 401
    assert (await s.client.post('/api/v1/auth/login', json=credentials)).status_code == 401
    assert (await s.client.post('/api/v1/auth/login', json={**credentials, 'otp_code': pyotp.TOTP(secret).now()})).status_code == 401
    future = (int(time.time()) // 30 + 2) * 30
    with patch('src.modules.identity.application.mfa.time', SimpleNamespace(time=lambda: future)):
        result = await s.client.post('/api/v1/auth/login', json={**credentials, 'otp_code': pyotp.TOTP(secret).at(future)})
    assert result.status_code == 200, result.text
    tokens = result.json()['data']
    auth = {'Authorization': 'Bearer ' + tokens['access_token']}
    assert (await s.client.get('/api/v1/auth/me', headers=auth)).status_code == 200
    refresh = await s.client.post('/api/v1/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    assert refresh.status_code == 200, refresh.text
    with patch('src.modules.identity.application.mfa.time', SimpleNamespace(time=lambda: future + 60)):
        result = await s.client.post('/api/v1/auth/mfa/disable', headers=auth, json={
            'password': 'Test-password-391', 'otp_code': pyotp.TOTP(secret).at(future + 60)})
    assert result.status_code == 200, result.text
    assert (await s.client.get('/api/v1/auth/me', headers=auth)).status_code == 401
    assert (await s.client.post('/api/v1/auth/refresh', json={'refresh_token': refresh.json()['data']['refresh_token']})).status_code == 401
    assert (await s.client.post('/api/v1/auth/login', json=credentials)).status_code == 200
    async with AsyncSessionFactory() as db:
        actions = (await db.execute(select(AuditLog.action).where(AuditLog.user_id == s.users['admin'].id))).scalars().all()
        assert {'MFA_SETUP', 'MFA_ENABLE', 'MFA_DISABLE'} <= set(actions)


@pytest.mark.asyncio
async def test_password_and_rate_limit(setup):
    for _ in range(10):
        response = await setup.client.post('/api/v1/auth/mfa/setup', headers=headers(setup), json={'password': 'incorrect'})
        assert response.status_code == 401
    response = await setup.client.post('/api/v1/auth/mfa/setup', headers=headers(setup), json={'password': 'incorrect'})
    assert response.status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize('statement', ['UPDATE audit.audit_log SET action=action WHERE false',
                                      'DELETE FROM audit.audit_log WHERE false', 'TRUNCATE audit.audit_log'])
async def test_audit_table_rejects_mutation(setup, statement):
    async with AsyncSessionFactory() as db:
        with pytest.raises(Exception, match='append-only'):
            await db.execute(text(statement))
        await db.rollback()


@pytest.mark.asyncio
async def test_expired_enrollment_and_audit_failure_are_atomic(setup):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    s = setup
    body = {'password': 'Test-password-391'}
    response = await s.client.post('/api/v1/auth/mfa/setup', headers=headers(s), json=body)
    secret = response.json()['data']['secret']
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users['admin'].id).values(
            totp_pending_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    response = await s.client.post('/api/v1/auth/mfa/enable', headers=headers(s), json={**body, 'otp_code': pyotp.TOTP(secret).now()})
    assert response.status_code == 401
    # An audit insert failure cannot leave MFA configuration changed.
    from src.modules.identity.application.mfa import MfaService
    async with AsyncSessionFactory() as db:
        original = db.add
        def fail_audit(row):
            if isinstance(row, AuditLog):
                raise RuntimeError('audit unavailable')
            original(row)
        with patch.object(db, 'add', side_effect=fail_audit):
            with pytest.raises(RuntimeError, match='audit unavailable'):
                await MfaService(db).manage(s.users['admin'].public_id, body['password'], None, 'setup')
        await db.rollback()
        row = await db.scalar(select(User).where(User.id == s.users['admin'].id))
        assert cipher().decrypt(row.totp_pending_secret.encode()).decode() == secret


@pytest.mark.asyncio
async def test_same_code_cannot_win_concurrent_logins(setup):
    import asyncio
    s = setup
    password = 'Test-password-391'
    response = await s.client.post('/api/v1/auth/mfa/setup', headers=headers(s), json={'password': password})
    secret = response.json()['data']['secret']
    response = await s.client.post('/api/v1/auth/mfa/enable', headers=headers(s), json={
        'password': password, 'otp_code': pyotp.TOTP(secret).now()})
    assert response.status_code == 200
    future = (int(time.time()) // 30 + 2) * 30
    credentials = {'email': s.users['admin'].email, 'password': password, 'otp_code': pyotp.TOTP(secret).at(future)}
    with patch('src.modules.identity.application.mfa.time', SimpleNamespace(time=lambda: future)):
        responses = await asyncio.gather(*(s.client.post('/api/v1/auth/login', json=credentials) for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
