"""Unit tests — OccupancyService event handling with a fake repository."""
import uuid

import pytest

from src.modules.occupancy.application.services import OccupancyService


class FakeOccupancyRepository:

    def __init__(self):
        self.created = []

    async def create(self, entity):
        self.created.append(entity)
        return entity


@pytest.fixture
def repo():
    return FakeOccupancyRepository()


async def test_handle_occupancy_event_persists_reading(repo):
    svc = OccupancyService(repo)
    body = {
        "enterprise_id": str(uuid.uuid4()),
        "zone_id": str(uuid.uuid4()),
        "camera_id": str(uuid.uuid4()),
        "count": 7,
    }
    entry = await svc.handle_occupancy_event(body)
    assert len(repo.created) == 1
    assert entry.current_count == 7
    assert str(entry.zone_id) == body["zone_id"]
    assert entry.shift_id is None


async def test_to_dict_serializes_uuids_and_timestamps(repo):
    svc = OccupancyService(repo)
    entry = await svc.handle_occupancy_event({
        "enterprise_id": str(uuid.uuid4()),
        "zone_id": str(uuid.uuid4()),
        "camera_id": str(uuid.uuid4()),
        "count": 3,
    })
    d = svc.to_dict(entry)
    assert d["current_count"] == 3
    assert isinstance(d["zone_id"], str)
    assert "T" in d["timestamp"]  # ISO format
