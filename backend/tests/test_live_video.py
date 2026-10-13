"""Per-asset authorization against PostgreSQL/Redis; origin requests mocked."""
import os
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from tests.test_review_integration import setup as integration_setup, headers
from src.core.settings import settings
from src.modules.camera.api import live
from src.shared.database.models import Camera, User
from src.shared.database.session import AsyncSessionFactory

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable database and Redis")
setup = integration_setup


@pytest.fixture
def origin(setup, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_HLS_URL", "http://media.internal:8888")
    monkeypatch.setattr(settings, "MEDIA_CAMERA_PATHS", {p.camera.public_id: f"camera-{i}" for i, p in enumerate(setup.places)})
    mock = AsyncMock(return_value=b"#EXTM3U\nstream.m3u8\n")
    monkeypatch.setattr(live, "fetch_asset", mock)
    return mock


def url(place, asset="index.m3u8"):
    return f"/api/v1/cameras/{place.camera.public_id}/live/{asset}"


async def test_every_asset_requires_current_camera_scope(setup, origin):
    s = setup
    for asset in ["index.m3u8", "stream.m3u8", "init.mp4", "seg1.mp4"]:
        for actor in ["admin", "manager", "viewer"]:
            response = await s.client.get(url(s.places[0], asset), headers=headers(s, actor))
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
        origin.reset_mock()
        assert (await s.client.get(url(s.places[0], asset))).status_code == 401
        assert (await s.client.get(url(s.places[0], asset), headers=headers(s, "foreign"))).status_code == 404
        for actor in ["manager", "viewer"]:
            assert (await s.client.get(url(s.places[1], asset), headers=headers(s, actor))).status_code == 404
        origin.assert_not_awaited()


@pytest.mark.parametrize("change", ["logout", "suspended", "scope", "password", "deleted", "inactive", "maintenance"])
async def test_open_stream_loses_access_on_next_request(setup, origin, change):
    s = setup
    h = headers(s, "viewer")
    assert (await s.client.get(url(s.places[0]), headers=h)).status_code == 200
    if change == "logout":
        assert (await s.client.post("/api/v1/auth/logout", headers=h)).status_code == 200
    else:
        async with AsyncSessionFactory() as db:
            if change in {"suspended", "scope", "password"}:
                values = {"suspended": {"status": "Inactive"}, "scope": {"assigned_zone_ids": [s.places[1].zone.public_id]},
                          "password": {"password_hash": "changed"}}[change]
                await db.execute(update(User).where(User.id == s.users["viewer"].id).values(**values))
            else:
                values = {"deleted": {"deleted_at": datetime.now(timezone.utc)}, "inactive": {"status": "Inactive"},
                          "maintenance": {"in_maintenance": True}}[change]
                await db.execute(update(Camera).where(Camera.id == s.places[0].camera.id).values(**values))
            await db.commit()
    origin.reset_mock()
    assert (await s.client.get(url(s.places[0], "seg2.mp4"), headers=h)).status_code in {401, 404, 409}
    origin.assert_not_awaited()


async def test_unconfigured_and_malformed_requests_never_contact_origin(setup, origin, monkeypatch):
    s = setup
    for asset in ["secrets.txt", "..%2Fother%2Fseg.mp4", "index.m3u8?url=http://evil.invalid", "index.m3u8?token=secret"]:
        assert (await s.client.get(url(s.places[0], asset), headers=headers(s))).status_code in {400, 404}
    monkeypatch.setattr(settings, "MEDIA_CAMERA_PATHS", {})
    assert (await s.client.get(url(s.places[0]), headers=headers(s))).status_code == 404
    origin.assert_not_awaited()


@pytest.mark.skipif(not os.environ.get("TEST_MEDIA_HLS_URL"), reason="Optional synthetic MediaMTX relay smoke")
async def test_real_media_relay_through_authorized_gateway(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(settings, "MEDIA_HLS_URL", os.environ["TEST_MEDIA_HLS_URL"])
    monkeypatch.setattr(settings, "MEDIA_HLS_SECRET", os.environ["TEST_MEDIA_HLS_SECRET"])
    monkeypatch.setattr(settings, "MEDIA_CAMERA_PATHS", {s.places[0].camera.public_id: "factory-cam-01"})
    master = await s.client.get(url(s.places[0]), headers=headers(s, "viewer"))
    assert master.status_code == 200, master.text
    playlist_name = next(line for line in master.text.splitlines() if line and not line.startswith("#"))
    playlist = await s.client.get(url(s.places[0], playlist_name), headers=headers(s, "viewer"))
    assert playlist.status_code == 200, playlist.text
    init_name = re.search(r'URI="([^"]+)"', playlist.text).group(1)
    segment_name = next(line for line in playlist.text.splitlines() if line and not line.startswith("#"))
    for asset, box in [(init_name, b"ftyp"), (segment_name, b"moof")]:
        response = await s.client.get(url(s.places[0], asset), headers=headers(s, "viewer"))
        assert response.status_code == 200, response.text[:100]
        assert box in response.content[:100]
        assert "set-cookie" not in response.headers
