"""
AnalyticsService — aggregate safety KPIs from violations, alerts, and
occupancy logs. Read-only; every query is scoped by enterprise_id.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.models import Alert, OccupancyLog, PPEViolation, Zone

# Weight of each severity when computing the safety score penalty
_SEVERITY_WEIGHTS = {"Critical": 10, "High": 5, "Medium": 2, "Low": 1}


def _default_range(from_dt: datetime | None, to_dt: datetime | None) -> tuple[datetime, datetime]:
    to_dt = to_dt or datetime.now(timezone.utc)
    from_dt = from_dt or (to_dt - timedelta(days=30))
    return from_dt, to_dt


class AnalyticsService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def violations(
        self,
        enterprise_id: UUID,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        zone_id: UUID | None = None,
    ) -> dict:
        """Violation counts by day, by type, and by zone over the range."""
        from_dt, to_dt = _default_range(from_dt, to_dt)
        base = select(PPEViolation).where(
            PPEViolation.enterprise_id == enterprise_id,
            PPEViolation.created_on >= from_dt,
            PPEViolation.created_on <= to_dt,
            PPEViolation.is_false_positive.is_(False),
        )
        if zone_id:
            base = base.where(PPEViolation.zone_id == zone_id)
        sub = base.subquery()

        by_day = (await self._db.execute(
            select(func.date_trunc("day", sub.c.created_on).label("day"), func.count())
            .group_by("day").order_by("day")
        )).all()

        by_type = (await self._db.execute(
            select(sub.c.violation_type, func.count()).group_by(sub.c.violation_type)
        )).all()

        by_zone = (await self._db.execute(
            select(Zone.name, func.count())
            .select_from(sub.join(Zone, Zone.id == sub.c.zone_id))
            .group_by(Zone.name)
        )).all()

        total = (await self._db.execute(select(func.count()).select_from(sub))).scalar_one()

        return {
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "total": total,
            "by_day": [{"day": d.date().isoformat(), "count": c} for d, c in by_day],
            "by_type": [{"type": t, "count": c} for t, c in by_type],
            "by_zone": [{"zone": z, "count": c} for z, c in by_zone],
        }

    async def occupancy(
        self,
        enterprise_id: UUID,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        zone_id: UUID | None = None,
    ) -> dict:
        """Average and peak occupancy per zone over the range."""
        from_dt, to_dt = _default_range(from_dt, to_dt)
        q = (
            select(
                Zone.name,
                func.avg(OccupancyLog.current_count),
                func.max(OccupancyLog.current_count),
                Zone.max_occupancy,
            )
            .join(Zone, Zone.id == OccupancyLog.zone_id)
            .where(
                OccupancyLog.enterprise_id == enterprise_id,
                OccupancyLog.timestamp >= from_dt,
                OccupancyLog.timestamp <= to_dt,
            )
            .group_by(Zone.name, Zone.max_occupancy)
        )
        if zone_id:
            q = q.where(OccupancyLog.zone_id == zone_id)
        rows = (await self._db.execute(q)).all()
        return {
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "zones": [
                {
                    "zone": name,
                    "avg_occupancy": round(float(avg or 0), 1),
                    "peak_occupancy": peak,
                    "max_occupancy": cap,
                }
                for name, avg, peak, cap in rows
            ],
        }

    async def compliance(
        self,
        enterprise_id: UUID,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> dict:
        """Alert-resolution compliance: how many alerts were resolved, and how
        many within their SLA window."""
        from_dt, to_dt = _default_range(from_dt, to_dt)
        row = (await self._db.execute(
            select(
                func.count(),
                func.sum(case((Alert.status.in_(["Resolved", "FalsePositive"]), 1), else_=0)),
                func.sum(case(
                    (
                        (Alert.resolved_on.isnot(None))
                        & (Alert.sla_due_at.isnot(None))
                        & (Alert.resolved_on <= Alert.sla_due_at),
                        1,
                    ),
                    else_=0,
                )),
            ).where(
                Alert.enterprise_id == enterprise_id,
                Alert.created_on >= from_dt,
                Alert.created_on <= to_dt,
            )
        )).one()
        total, resolved, within_sla = row[0], int(row[1] or 0), int(row[2] or 0)
        return {
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "total_alerts": total,
            "resolved": resolved,
            "resolution_rate_pct": round(100 * resolved / total, 1) if total else 100.0,
            "within_sla": within_sla,
            "sla_compliance_pct": round(100 * within_sla / resolved, 1) if resolved else 100.0,
        }

    async def safety_score(
        self,
        enterprise_id: UUID,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> dict:
        """0–100 score: starts at 100 and subtracts severity-weighted alert
        counts normalized per day (min 0). A quiet factory scores 100."""
        from_dt, to_dt = _default_range(from_dt, to_dt)
        rows = (await self._db.execute(
            select(Alert.severity, func.count())
            .where(
                Alert.enterprise_id == enterprise_id,
                Alert.created_on >= from_dt,
                Alert.created_on <= to_dt,
                Alert.status != "FalsePositive",
            )
            .group_by(Alert.severity)
        )).all()

        days = max(1, (to_dt - from_dt).days)
        penalty = sum(_SEVERITY_WEIGHTS.get(sev, 1) * count for sev, count in rows) / days
        score = max(0.0, round(100.0 - penalty, 1))
        return {
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "score": score,
            "alerts_by_severity": {sev: count for sev, count in rows},
        }
