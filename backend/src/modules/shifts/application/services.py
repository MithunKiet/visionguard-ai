"""
ShiftService — shift CRUD + resolution of the currently active shift.

`find_active` handles overnight shifts (e.g. 22:00–06:00): a shift whose
end_time is before its start_time spans midnight and matches either the
evening of a configured day or the following morning.
"""
import uuid
from datetime import datetime, time, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import Shift

log = structlog.get_logger()

_DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class ShiftService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_shifts(self, enterprise_id: UUID, factory_id: UUID | None = None) -> list[dict]:
        q = select(Shift).where(Shift.enterprise_id == enterprise_id)
        if factory_id:
            q = q.where(Shift.factory_id == factory_id)
        rows = (await self._db.execute(q.order_by(Shift.start_time))).scalars()
        return [self.to_dict(s) for s in rows]

    async def create_shift(
        self,
        enterprise_id: UUID,
        factory_id: UUID,
        name: str,
        start_time: time,
        end_time: time,
        days: list[str],
    ) -> dict:
        row = Shift(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            factory_id=factory_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            days=[d.upper() for d in days],
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("shift.created", name=name, factory_id=str(factory_id))
        return self.to_dict(row)

    async def update_shift(self, shift_id: UUID, enterprise_id: UUID, changes: dict) -> dict:
        row = await self._get_row(shift_id, enterprise_id)
        for field in ("name", "start_time", "end_time", "days", "status"):
            if changes.get(field) is not None:
                value = changes[field]
                if field == "days":
                    value = [d.upper() for d in value]
                setattr(row, field, value)
        await self._db.commit()
        await self._db.refresh(row)
        return self.to_dict(row)

    async def delete_shift(self, shift_id: UUID, enterprise_id: UUID) -> None:
        row = await self._get_row(shift_id, enterprise_id)
        row.status = "Inactive"
        await self._db.commit()

    async def active_shifts(self, enterprise_id: UUID, at: datetime) -> list[dict]:
        q = select(Shift).where(
            Shift.enterprise_id == enterprise_id,
            Shift.status == "Active",
        )
        rows = (await self._db.execute(q)).scalars().all()
        return [self.to_dict(s) for s in rows if self.is_active_at(s, at)]

    async def find_active_for_factory(
        self, enterprise_id: UUID, factory_id: UUID, at: datetime
    ) -> Shift | None:
        q = select(Shift).where(
            Shift.enterprise_id == enterprise_id,
            Shift.factory_id == factory_id,
            Shift.status == "Active",
        )
        rows = (await self._db.execute(q)).scalars().all()
        for s in rows:
            if self.is_active_at(s, at):
                return s
        return None

    @staticmethod
    def is_active_at(shift: Shift, at: datetime) -> bool:
        now_t = at.time()
        today = _DAY_NAMES[at.weekday()]
        days = [d.upper() for d in (shift.days or [])]

        if shift.start_time <= shift.end_time:
            return today in days and shift.start_time <= now_t < shift.end_time

        # Overnight shift — active from start_time on a configured day until
        # end_time the next morning.
        if today in days and now_t >= shift.start_time:
            return True
        yesterday = _DAY_NAMES[(at - timedelta(days=1)).weekday()]
        return yesterday in days and now_t < shift.end_time

    async def _get_row(self, shift_id: UUID, enterprise_id: UUID) -> Shift:
        row = (await self._db.execute(
            select(Shift).where(Shift.id == shift_id, Shift.enterprise_id == enterprise_id)
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("Shift", str(shift_id))
        return row

    @staticmethod
    def to_dict(s: Shift) -> dict:
        return {
            "id": str(s.id),
            "factory_id": str(s.factory_id),
            "name": s.name,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "days": s.days,
            "status": s.status,
        }
