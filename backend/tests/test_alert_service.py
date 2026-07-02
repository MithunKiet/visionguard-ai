"""Unit tests — AlertService lifecycle rules, using an in-memory fake repository."""
import uuid
from datetime import datetime, timezone

import pytest

from src.core.exceptions import NotFoundException, VisionGuardException
from src.modules.alerts.application.services import AlertService
from src.modules.alerts.domain.entities import AlertEntity
from src.modules.ppe.domain.entities import ViolationEntity


class FakeAlertRepository:

    def __init__(self):
        self.alerts: dict = {}
        self.history: list = []

    async def create(self, entity: AlertEntity) -> AlertEntity:
        self.alerts[entity.id] = entity
        return entity

    async def get_by_id(self, alert_id, enterprise_id):
        alert = self.alerts.get(alert_id)
        if alert and alert.enterprise_id == enterprise_id:
            return alert
        return None

    async def exists_open(self, zone_id, camera_id, alert_type, cooldown_seconds) -> bool:
        return any(
            a.zone_id == zone_id and a.camera_id == camera_id
            and a.alert_type == alert_type and a.status in ("Open", "Acknowledged")
            for a in self.alerts.values()
        )

    async def next_sequence(self, enterprise_id) -> int:
        return len(self.alerts) + 1

    async def transition(self, alert_id, enterprise_id, to_status, changed_by, comment=None):
        alert = self.alerts[alert_id]
        self.history.append((alert.status, to_status, changed_by, comment))
        alert.status = to_status
        return alert

    async def assign(self, alert_id, enterprise_id, user_id) -> None:
        self.alerts[alert_id].assigned_to = user_id


def _violation(**overrides) -> ViolationEntity:
    defaults = dict(
        id=uuid.uuid4(),
        enterprise_id=uuid.uuid4(),
        zone_id=uuid.uuid4(),
        camera_id=uuid.uuid4(),
        violation_type="helmet_missing",
        confidence=0.92,
        snapshot_key="snap.jpg",
        track_id="T-1",
        shift_id=None,
        rule_id=None,
        is_false_positive=False,
        fp_reason=None,
        needs_review=False,
        created_on=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return ViolationEntity(**defaults)


@pytest.fixture
def repo():
    return FakeAlertRepository()


@pytest.fixture
def svc(repo):
    return AlertService(repo)


class TestCreateFromViolation:

    async def test_creates_alert_with_severity_mapping(self, svc):
        alert = await svc.create_from_violation(_violation(), factory_id=uuid.uuid4())
        assert alert is not None
        assert alert.severity == "Critical"          # helmet_missing → Critical
        assert alert.alert_type == "PPE_VIOLATION_HELMET"
        assert alert.status == "Open"
        assert alert.alert_number.startswith("ALT-")
        assert alert.sla_due_at > alert.created_on

    async def test_deduplicates_within_cooldown(self, svc):
        v = _violation()
        first = await svc.create_from_violation(v, factory_id=uuid.uuid4())
        duplicate = await svc.create_from_violation(v, factory_id=uuid.uuid4())
        assert first is not None
        assert duplicate is None

    async def test_event_alert_created_and_deduplicated(self, svc):
        args = dict(
            enterprise_id=uuid.uuid4(), factory_id=uuid.uuid4(),
            zone_id=uuid.uuid4(), camera_id=uuid.uuid4(),
            alert_type="OVERCROWDING", severity="High",
        )
        first = await svc.create_event_alert(**args)
        assert first is not None and first.alert_type == "OVERCROWDING"
        assert await svc.create_event_alert(**args) is None


class TestLifecycle:

    async def _open_alert(self, svc):
        return await svc.create_from_violation(_violation(), factory_id=uuid.uuid4())

    async def test_acknowledge_then_resolve(self, svc):
        alert = await self._open_alert(svc)
        user = uuid.uuid4()
        result = await svc.acknowledge(alert.id, alert.enterprise_id, user)
        assert result["status"] == "Acknowledged"
        result = await svc.resolve(alert.id, alert.enterprise_id, user, "fixed")
        assert result["status"] == "Resolved"

    async def test_cannot_resolve_twice(self, svc):
        alert = await self._open_alert(svc)
        user = uuid.uuid4()
        await svc.resolve(alert.id, alert.enterprise_id, user, None)
        with pytest.raises(VisionGuardException) as exc:
            await svc.resolve(alert.id, alert.enterprise_id, user, None)
        assert exc.value.code == "INVALID_TRANSITION"

    async def test_wrong_enterprise_is_not_found(self, svc):
        alert = await self._open_alert(svc)
        with pytest.raises(NotFoundException):
            await svc.acknowledge(alert.id, uuid.uuid4(), uuid.uuid4())

    async def test_false_positive_from_open(self, svc):
        alert = await self._open_alert(svc)
        result = await svc.mark_false_positive(
            alert.id, alert.enterprise_id, uuid.uuid4(), "reflection"
        )
        assert result["status"] == "FalsePositive"
