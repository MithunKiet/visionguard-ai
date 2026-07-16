"""
ShiftService — shift CRUD + resolution of the currently active shift.

`find_active` handles overnight shifts (e.g. 22:00-06:00): a shift whose
end_time is before its start_time spans midnight and matches either the
evening of a configured day or the following morning.
"""
from datetime import datetime, time, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import Enterprise, Factory, Shift
from src.shared.database.pid import to_pk, to_public_id

log = structlog.get_logger()

_DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class ShiftService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_shifts(self, enterprise_id: str, factory_id: str | None = None) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Shift).where(Shift.enterprise_id == ent_pk)
        if factory_id:
            q = q.where(Shift.factory_id == await to_pk(self._db, Factory, factory_id))
        rows = (await self._db.execute(q.order_by(Shift.start_time))).scalars()
        return [await self.to_dict(self._db, s) for s in rows]

    async def create_shift(
        self,
        enterprise_id: str,
        factory_id: str,
        name: str,
        start_time: time,
        end_time: time,
        days: list[str],
    ) -> dict:
        row = Shift(
            enterprise_id=await to_pk(self._db, Enterprise, enterprise_id),
            factory_id=await to_pk(self._db, Factory, factory_id),
            name=name,
            start_time=start_time,
            end_time=end_time,
            days=[d.upper() for d in days],
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("shift.created", name=name, factory_id=str(factory_id))
        return await self.to_dict(self._db, row)

    async def update_shift(self, shift_id: str, enterprise_id: str, changes: dict) -> dict:
        row = await self._get_row(shift_id, enterprise_id)
        for field in ("name", "start_time", "end_time", "days", "status"):
            if changes.get(field) is not None:
                value = changes[field]
                if field == "days":
                    value = [d.upper() for d in value]
                setattr(row, field, value)
        await self._db.commit()
        await self._db.refresh(row)
        return await self.to_dict(self._db, row)

    async def delete_shift(self, shift_id: str, enterprise_id: str) -> None:
        row = await self._get_row(shift_id, enterprise_id)
        row.status = "Inactive"
        await self._db.commit()

    async def active_shifts(self, enterprise_id: str, at: datetime) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Shift).where(
            Shift.enterprise_id == ent_pk,
            Shift.status == "Active",
        )
        rows = (await self._db.execute(q)).scalars().all()
        return [await self.to_dict(self._db, s) for s in rows if self.is_active_at(s, at)]

    async def find_active_for_factory(
        self, enterprise_id: str, factory_id: str, at: datetime
    ) -> Shift | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        factory_pk = await to_pk(self._db, Factory, factory_id)
        q = select(Shift).where(
            Shift.enterprise_id == ent_pk,
            Shift.factory_id == factory_pk,
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

    async def _get_row(self, shift_id: str, enterprise_id: str) -> Shift:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        row = (await self._db.execute(
            select(Shift).where(Shift.public_id == shift_id, Shift.enterprise_id == ent_pk)
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("Shift", str(shift_id))
        return row

    @staticmethod
    async def to_dict(db: AsyncSession, s: Shift) -> dict:
        return {
            "id": s.public_id,
            "factory_id": await to_public_id(db, Factory, s.factory_id),
            "name": s.name,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "days": s.days,
            "status": s.status,
        }
