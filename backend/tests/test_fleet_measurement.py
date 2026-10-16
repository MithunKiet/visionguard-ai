"""Unsafe targets and invalid performance gates must not start a workload."""
from argparse import Namespace
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("measure_fleet", Path(__file__).resolve().parents[1] / "scripts/measure_fleet.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def settings():
    return Namespace(factories=5, cameras_per_factory=200, workers_per_factory=4, seconds=60,
        events_per_second=10, reads_per_second=6, history_events=1000, history_cameras=100, p95_ms=750, event_p95_ms=2000)


@pytest.mark.parametrize("database", ["production", "visionguard", "visionguard_test", "capacity_test_copy"])
def test_measurement_refuses_non_dedicated_database(monkeypatch, database):
    monkeypatch.setenv("CAPACITY_DATABASE_URL", f"postgresql+asyncpg://localhost/{database}")
    with pytest.raises(ValueError, match="dedicated"):
        measure.validate_args(settings())


@pytest.mark.parametrize("field,value", [("events_per_second", 101), ("factories", 0), ("workers_per_factory", 3),
    ("p95_ms", float("nan")), ("event_p95_ms", float("inf")), ("history_events", 0), ("seconds", 301)])
def test_invalid_bounds_fail_before_workload(monkeypatch, field, value):
    monkeypatch.setenv("CAPACITY_DATABASE_URL", "postgresql+asyncpg://localhost/fleet_capacity_test")
    monkeypatch.setenv("ENVIRONMENT", "development")
    args = settings()
    setattr(args, field, value)
    with pytest.raises(ValueError):
        measure.validate_args(args)


def test_production_mode_refused_even_for_test_named_database(monkeypatch):
    monkeypatch.setenv("CAPACITY_DATABASE_URL", "postgresql+asyncpg://localhost/fleet_capacity_test")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="isolated"):
        measure.validate_args(settings())
