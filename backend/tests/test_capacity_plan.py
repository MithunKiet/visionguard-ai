import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("capacity_plan", Path(__file__).resolve().parents[2] / "infra/capacity/plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def evidence():
    return {"scope": "integrated_camera_pilot", "hardware_id": "test-fixture", "evidence_reference": "test-fixture",
            "model_sha256": "a" * 64, "observation_hours": 24, "components_tested": sorted(plan.REQUIRED_COMPONENTS),
            "failover_drill_passed": True, "lost_events": 0, "failed_notifications": 0, "stale_frame_events": 0,
            "peak_cpu_fraction": 0.5, "peak_ram_fraction": 0.6, "peak_gpu_memory_fraction": 0.7,
            "cameras": [{"camera_id": str(i), "target_fps": 2, "processed_fps": 2,
                         "capture_to_alert_p95_seconds": 3, "inference_errors": 0} for i in range(10)]}


def test_headroom_and_failure_reserve_are_applied_without_certifying_production():
    result = plan.calculate(evidence(), 20)
    assert result["planned_cameras_per_worker"] == 7
    assert result["active_workers"] == 3 and result["total_workers"] == 4
    assert result["remaining_capacity_after_reserved_worker_failures"] >= 20
    assert result["production_approved"] is False and result["evidence_independently_verified"] is False


@pytest.mark.parametrize("field,value", [("scope", "inference_only"), ("observation_hours", 1),
    ("lost_events", 1), ("lost_events", False), ("stale_frame_events", None),
    ("peak_gpu_memory_fraction", float("nan")), ("peak_ram_fraction", 0.95),
    ("components_tested", []), ("failover_drill_passed", False), ("model_sha256", "")])
def test_missing_or_failed_evidence_never_produces_worker_counts(field, value):
    data = evidence()
    data[field] = value
    result = plan.calculate(data, 20)
    assert result["status"] == "insufficient_evidence"
    assert "total_workers" not in result


@pytest.mark.parametrize("field,value", [("processed_fps", 0), ("inference_errors", 1),
    ("capture_to_alert_p95_seconds", 30), ("target_fps", None), ("camera_id", "1")])
def test_one_underperforming_camera_blocks_the_plan(field, value):
    data = evidence()
    data["cameras"][0][field] = value
    assert plan.calculate(data, 20)["status"] == "insufficient_evidence"


def test_example_is_explicitly_unmeasured():
    import json
    path = Path(__file__).resolve().parents[2] / "infra/capacity/pilot.example.json"
    assert plan.calculate(json.loads(path.read_text()), 20)["status"] == "insufficient_evidence"
