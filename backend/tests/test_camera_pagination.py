"""Scoped camera pagination, search and legacy list compatibility."""
import os
from uuid import uuid4

import pytest
from src.shared.database.models import Camera
from src.shared.database.session import AsyncSessionFactory
from tests.test_review_integration import setup as setup, headers

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='Requires disposable PostgreSQL and Redis')


async def test_pages_search_scope_and_legacy_inventory(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        for location, count in [(s.places[0], 61), (s.places[1], 3), (s.places[2], 4)]:
            db.add_all([Camera(enterprise_id=location.factory.enterprise_id, factory_id=location.factory.id,
                zone_id=location.zone.id, name='Pagination fixture', code=f'PAGE_{uuid4().hex}', rtsp_url='rtsp://user:secret@camera.invalid/feed',
                status='Inactive', is_active=False) for _ in range(count)])
        await db.commit()
    async def get(caller='admin', **params):
        response = await s.client.get('/api/v1/cameras', headers=headers(s, caller), params=params)
        assert response.status_code == 200, response.text
        assert 'secret' not in response.text
        return response.json()
    first = await get(page=1, page_size=50, search='Pagination fixture')
    second = await get(page=2, page_size=50, search='Pagination fixture')
    assert first['meta']['total'] == 64 and len(first['data']) == 50 and len(second['data']) == 14
    ids = [row['id'] for row in first['data'] + second['data']]
    assert len(set(ids)) == 64
    assert [row['id'] for row in (await get(page=1, search='Pagination fixture'))['data']] == ids[:50]
    assert (await get('manager', page=1, search='Pagination fixture'))['meta']['total'] == 61
    assert (await get('foreign', page=1, search='Pagination fixture'))['meta']['total'] == 4
    assert (await get(page=1, search='%'))['meta']['total'] == 0
    assert (await get(page=1, search='PAGE_'))['meta']['total'] == 64
    assert (await get(page=3, search='Pagination fixture'))['data'] == []
    legacy = await get()
    assert legacy['meta'] is None and len(legacy['data']) >= 64
    assert len((await get(page_size=2))['data']) == 2
    for params in [{'page': 0}, {'page_size': 101}, {'search': 'x' * 101}]:
        assert (await s.client.get('/api/v1/cameras', headers=headers(s), params=params)).status_code == 422
