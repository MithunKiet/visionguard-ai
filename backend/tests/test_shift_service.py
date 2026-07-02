"""Unit tests — ShiftService.is_active_at, including overnight shifts."""
from datetime import datetime, time, timezone
from types import SimpleNamespace

from src.modules.shifts.application.services import ShiftService


def _shift(start: time, end: time, days: list[str]) -> SimpleNamespace:
    return SimpleNamespace(start_time=start, end_time=end, days=days)


# 2026-07-01 is a Wednesday
WED_10AM = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
WED_11PM = datetime(2026, 7, 1, 23, 0, tzinfo=timezone.utc)
THU_3AM = datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc)
SUN_10AM = datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc)


class TestDayShift:
    shift = _shift(time(8, 0), time(17, 0), ["MON", "TUE", "WED", "THU", "FRI"])

    def test_active_during_shift_hours(self):
        assert ShiftService.is_active_at(self.shift, WED_10AM)

    def test_inactive_after_hours(self):
        assert not ShiftService.is_active_at(self.shift, WED_11PM)

    def test_inactive_on_unconfigured_day(self):
        assert not ShiftService.is_active_at(self.shift, SUN_10AM)


class TestOvernightShift:
    shift = _shift(time(22, 0), time(6, 0), ["WED"])

    def test_active_in_evening_of_configured_day(self):
        assert ShiftService.is_active_at(self.shift, WED_11PM)

    def test_active_next_morning_before_end(self):
        assert ShiftService.is_active_at(self.shift, THU_3AM)

    def test_inactive_midday(self):
        assert not ShiftService.is_active_at(self.shift, WED_10AM)
