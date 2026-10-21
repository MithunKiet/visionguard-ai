"""Camera import transaction, credential privacy and admission regressions."""
import asyncio
import csv
import io
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.modules.camera.application import imports
from src.shared.database.models import AuditLog, Camera, CameraImport, User, Zone
from src.shared.database.session import AsyncSessionFactory
from tests.test_review_integration import setup as setup, headers

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


def content(s, count=1, **override):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['name', 'code', 'zone_id', 'rtsp_url', 'factory_id', 'fps'])
    writer.writeheader()
    batch = uuid4().hex
    for index in range(count):
        writer.writerow({'name': f'Imported {index}', 'code': f'{batch}-{index}', 'zone_id': s.places[0].zone.public_id,
                         'rtsp_url': f'rtsp://operator:private-secret@camera.example.invalid/{batch}/{index}?channel={index}',
                         'factory_id': s.places[0].factory.public_id, 'fps': '2', **override})
    return stream.getvalue()


async def preview(s, text, caller='admin'):
    return await s.client.post('/api/v1/cameras/import/preview', headers=headers(s, caller), json={'csv_text': text})


async def submit(s, text, token, key=None, caller='admin'):
    return await s.client.post('/api/v1/cameras/import/commit', headers=headers(s, caller),
                              json={'csv_text': text, 'preview_token': token, 'request_key': key or str(uuid4())})


async def test_preview_atomic_import_retry_and_explicit_admission(setup):
    from src.modules.worker.infrastructure.scheduling import WorkerSchedulingRepository
    s = setup
    text = content(s, 3)
    checked = await preview(s, text)
    assert checked.status_code == 200 and checked.json()['data']['valid']
    assert checked.headers['cache-control'] == 'no-store'
    assert 'private-secret' not in checked.text and 'rtsp://' not in checked.text
    key = str(uuid4())
    token = checked.json()['data']['preview_token']
    response = await submit(s, text, token, key)
    assert response.status_code == 200, response.text
    ids = [row['id'] for row in response.json()['data']['cameras']]
    replay = await submit(s, text, 'expired-or-lost-token', key)
    assert replay.status_code == 200 and replay.json()['data']['replayed']
    assert [row['id'] for row in replay.json()['data']['cameras']] == ids
    async with AsyncSessionFactory() as db:
        rows = list(await db.scalars(select(Camera).where(Camera.public_id.in_(ids))))
        assert len(rows) == 3 and all(row.status == 'Inactive' and not row.is_active and row.worker_id is None for row in rows)
        assert await db.scalar(select(func.count()).select_from(CameraImport).where(CameraImport.request_key == key)) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == key, AuditLog.action == 'CAMERAS_IMPORTED')) == 1
        assert await WorkerSchedulingRepository(db).admit_pending(s.enterprise.public_id, camera_id=ids[0]) == {}
    # Publication mocked to avoid external effects; admission opens only after explicit activation.
    from unittest.mock import patch
    with patch('src.shared.messaging.publisher.publish_config_event', AsyncMock()):
        response = await s.client.patch(f'/api/v1/cameras/{ids[0]}/status', headers=headers(s), json={'status': 'Active'})
    assert response.status_code == 200
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(Camera.is_active).where(Camera.public_id == ids[0])) is True
    assert 'private-secret' not in response.text


@pytest.mark.parametrize('changes', [{'fps': 'nan'}, {'fps': 'inf'}, {'fps': '-1'}, {'fps': '31'}, {'name': ''},
                                    {'code': '=FORMULA()'}, {'zone_id': 'not-a-uuid'}, {'rtsp_url': 'rtsp://private-secret@localhost/feed'}])
async def test_invalid_rows_never_receive_commit_token(setup, changes):
    response = await preview(setup, content(setup, **changes))
    assert response.status_code == 200
    assert not response.json()['data']['valid'] and response.json()['data']['preview_token'] is None
    assert 'private-secret' not in response.text


async def test_scope_factory_mapping_and_viewers(setup):
    s = setup
    assert (await preview(s, content(s), 'viewer')).status_code == 403
    assert (await submit(s, content(s), 'anything', caller='viewer')).status_code == 403
    for location in (s.places[1], s.places[2]):
        response = await preview(s, content(s, zone_id=location.zone.public_id, factory_id=location.factory.public_id), 'manager')
        assert not response.json()['data']['valid']
        assert response.json()['data']['rows'][0]['zone_name'] is None
    assert not (await preview(s, content(s, factory_id=s.places[1].factory.public_id))).json()['data']['valid']


async def test_duplicates_and_concurrent_commit_have_one_winner(setup):
    s = setup
    text = content(s, 2, code='DUPLICATE')
    assert not (await preview(s, text)).json()['data']['valid']
    text = content(s, 2, rtsp_url='rtsp://a:private-secret@camera.example.invalid/duplicate')
    assert not (await preview(s, text)).json()['data']['valid']
    text = content(s)
    token = (await preview(s, text)).json()['data']['preview_token']
    replies = await asyncio.gather(submit(s, text, token), submit(s, text, token))
    assert sorted(reply.status_code for reply in replies) == [200, 409]
    assert not (await preview(s, text)).json()['data']['valid']
    assert all('private-secret' not in reply.text for reply in replies)


async def test_concurrent_same_request_replays_one_result(setup):
    s = setup
    text = content(s)
    token = (await preview(s, text)).json()['data']['preview_token']
    key = str(uuid4())
    replies = await asyncio.gather(*(submit(s, text, token, key) for _ in range(2)))
    assert [reply.status_code for reply in replies] == [200, 200]
    assert sorted(reply.json()['data']['replayed'] for reply in replies) == [False, True]
    assert replies[0].json()['data']['cameras'] == replies[1].json()['data']['cameras']


async def test_changed_input_actor_and_scope_are_rechecked(setup):
    s = setup
    text = content(s)
    token = (await preview(s, text, 'manager')).json()['data']['preview_token']
    assert (await submit(s, text.replace('Imported 0', 'Changed'), token, caller='manager')).status_code == 409
    assert (await submit(s, text, token, caller='admin')).status_code == 409
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users['manager'].id).values(factory_id=s.places[1].factory.id))
        await db.commit()
    assert (await submit(s, text, token, caller='manager')).status_code == 409


async def test_inactive_zone_and_malformed_oversized_csv_fail_closed(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        await db.execute(update(Zone).where(Zone.id == s.places[0].zone.id).values(status='Inactive'))
        await db.commit()
    assert not (await preview(s, content(s))).json()['data']['valid']
    for text in ['', 'name,code,zone_id,rtsp_url,name\na,b,c,d,e', content(s, 201)]:
        response = await preview(s, text)
        assert response.status_code == 422 and 'private-secret' not in response.text
    response = await preview(s, 'private-secret' * (imports.MAX_BYTES // 10))
    assert response.status_code == 413 and 'private-secret' not in response.text


async def test_failed_audit_rolls_back_every_camera(setup, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.exc import SQLAlchemyError
    s = setup
    text = content(s, 3)
    token = (await preview(s, text)).json()['data']['preview_token']
    key = str(uuid4())
    original = AsyncSession.add
    def reject_audit(db, instance, **kwargs):
        if isinstance(instance, AuditLog) and instance.action == 'CAMERAS_IMPORTED':
            raise SQLAlchemyError('private-secret must not leak')
        return original(db, instance, **kwargs)
    monkeypatch.setattr(AsyncSession, 'add', reject_audit)
    response = await submit(s, text, token, key)
    assert response.status_code == 503 and 'private-secret' not in response.text
    async with AsyncSessionFactory() as db:
        assert not await db.scalar(select(CameraImport.id).where(CameraImport.request_key == key))
        codes = [row['code'] for row in imports.parse_csv(text)]
        assert not await db.scalar(select(Camera.id).where(Camera.code.in_(codes)))


async def test_200_rows_commit_in_one_batch(setup):
    text = content(setup, 200)
    token = (await preview(setup, text)).json()['data']['preview_token']
    response = await submit(setup, text, token)
    assert response.status_code == 200, response.text
    assert len(response.json()['data']['cameras']) == 200


async def test_normal_create_cannot_bypass_import_duplicate_guard(setup):
    s = setup
    text = content(s)
    token = (await preview(s, text)).json()['data']['preview_token']
    assert (await submit(s, text, token)).status_code == 200
    row = imports.parse_csv(text)[0]
    response = await s.client.post('/api/v1/cameras', headers=headers(s), json={key: row[key] for key in ['name', 'code', 'zone_id', 'rtsp_url']})
    assert response.status_code == 409


async def test_expired_preview_and_replay_access_are_enforced(setup):
    import jwt
    from src.core.settings import settings
    s = setup
    text = content(s)
    token = (await preview(s, text, 'manager')).json()['data']['preview_token']
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    claims['exp'] = 1
    expired = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    assert (await submit(s, text, expired, caller='manager')).status_code == 409
    key = str(uuid4())
    assert (await submit(s, text, token, key, 'manager')).status_code == 200
    assert (await submit(s, text + '\n', token, key, 'manager')).status_code == 409
    assert (await submit(s, text, token, key, 'admin')).status_code == 409
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users['manager'].id).values(factory_id=s.places[1].factory.id))
        await db.commit()
    response = await submit(s, text, token, key, 'manager')
    assert response.status_code == 404 and 'private-secret' not in response.text
