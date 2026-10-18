"""P7 evidence policy tests use synthetic documents, never real acceptance results."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pilot_acceptance", ROOT / "infra/pilot/acceptance.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
NOW = datetime.now(timezone.utc).replace(microsecond=0)
START = NOW - timedelta(hours=26)
END = NOW - timedelta(hours=1)


def save(root, name, value):
    content = json.dumps(value).encode()
    (root / name).write_bytes(content)
    return {"path": name, "sha256": pilot.digest(content)}


@pytest.fixture
def case(tmp_path):
    contract = json.loads((ROOT / "infra/pilot/contract.example.json").read_text())
    contract.update(enterprise_id=str(uuid4()), factory_id=str(uuid4()), site_owner="Test owner",
                    approved_by="Test reviewer", approved_at=(START - timedelta(hours=1)).isoformat(),
                    camera_ids=[str(uuid4()) for _ in range(10)])
    contract["release"] = {key: "a" * (40 if key == "git_commit" else 64) for key in contract["release"]}
    release_evidence = {key: save(tmp_path, key + "-inventory.json", {"synthetic_test_inventory": key})
                        for key in ("images", "hardware", "configuration")}
    for key, inventory in release_evidence.items():
        contract["release"][key + "_sha256"] = inventory["sha256"]
    contract["policy"] = dict.fromkeys(pilot.POLICIES, 1)
    contract["policy"].update(min_event_precision=0.95, min_event_recall=0.9)
    ref = save(tmp_path, "contract.json", contract)
    bundle = {"schema_version": 1, "scope": "real_factory_pilot", "contract": ref,
              "started_at": START.isoformat(), "ended_at": END.isoformat(), "gates": {},
              "release_evidence": release_evidence}
    for gate, checks in pilot.CHECKS.items():
        report = {"synthetic_test_fixture": True}
        if gate == "model":
            report.update(status="model_ready", scope="startup_smoke", gpu_available=True, actual_device="cuda:0",
                          model_sha256="a" * 64, created_at=START.isoformat())
        elif gate == "monitoring":
            report.update(status="pass", errors=[], error_counts={}, expected_workers=2, registered_workers=2,
                          active_targets=2, checked_at=END.isoformat())
        metrics = {}
        for key, (op, target) in pilot.METRICS.get(gate, {}).items():
            metrics[key] = contract["policy"][target] if isinstance(target, str) else target
        bundle["gates"][gate] = {"status": "pass", "reviewer": "Test reviewer", "summary": "Synthetic fixture only",
            "observed_at": END.isoformat(), "contract_sha256": ref["sha256"],
            "checks": dict.fromkeys(checks, True), "measurements": metrics,
            "evidence": [save(tmp_path, gate + ".json", report)]}
    return bundle, contract, tmp_path


def evaluate(case):
    bundle, _, root = case
    return pilot.evaluate(bundle, root, NOW)


def update_contract(case):
    bundle, contract, root = case
    bundle["contract"] = save(root, "contract.json", contract)
    for row in bundle["gates"].values():
        row["contract_sha256"] = bundle["contract"]["sha256"]


def test_complete_fixture_only_becomes_ready_for_human_review(case):
    result = evaluate(case)
    assert result["status"] == "ready_for_site_review"
    assert not result["production_approved"] and not result["evidence_independently_verified"]
    assert result["camera_count"] == 10


def test_cli_evaluates_complete_synthetic_bundle_without_approving_production(case):
    bundle, _, root = case
    save(root, "bundle.json", bundle)
    output = root / "result.json"
    result = subprocess.run([sys.executable, str(ROOT / "infra/pilot/acceptance.py"),
        "--bundle", str(root / "bundle.json"), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0
    report = json.loads(output.read_text())
    assert report["status"] == "ready_for_site_review" and report["production_approved"] is False
    assert report["bundle_sha256"] == pilot.digest((root / "bundle.json").read_bytes())


@pytest.mark.parametrize("gate", list(pilot.CHECKS))
def test_no_gate_can_be_omitted(case, gate):
    del case[0]["gates"][gate]
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "0", 1, 10 ** 1000])
def test_losses_and_invalid_measurements_block(case, value):
    case[0]["gates"]["soak"]["measurements"]["lost_events"] = value
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("gate,metric,value", [
    ("accuracy", "minimum_event_precision", 0.9), ("accuracy", "minimum_event_recall", 0.8),
    ("accuracy", "minimum_event_precision", 1.1), ("accuracy", "minimum_positive_episodes_per_cell", 0),
    ("accuracy", "minimum_positive_episodes_per_cell", 1.5),
    ("capacity", "peak_ram_fraction", 0.9), ("capacity", "capture_to_alert_p95_seconds", 2),
    ("soak", "continuous_hours", 23), ("soak", "continuous_hours", 26),
    ("failover", "worst_recovery_seconds", 2), ("failover", "overlapping_authorized_owners", 1),
    ("restore", "data_loss_seconds", 2), ("delivery", "pending_at_drain_end", 1),
])
def test_failed_site_measurements_block(case, gate, metric, value):
    case[0]["gates"][gate]["measurements"][metric] = value
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("field,value", [("status", "pending"), ("reviewer", ""), ("evidence", []),
    ("observed_at", START.replace(tzinfo=None).isoformat()), ("observed_at", NOW.isoformat()),
    ("contract_sha256", "b" * 64)])
def test_failed_missing_or_mismatched_attestation_blocks(case, field, value):
    case[0]["gates"]["restore"][field] = value
    assert evaluate(case)["status"] == "blocked"


def test_false_review_check_blocks(case):
    case[0]["gates"]["security"]["checks"]["tenant_isolation_tested"] = False
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("change", ["late_contract", "duplicate_camera", "too_few", "stale", "future",
                                     "unsupported_ppe", "missing_policy", "zero_recall", "boolean_target"])
def test_invalid_contract_or_window_blocks(case, change):
    bundle, contract, _ = case
    if change == "late_contract":
        contract["approved_at"] = END.isoformat()
    elif change == "duplicate_camera":
        contract["camera_ids"][0] = contract["camera_ids"][1]
    elif change == "too_few":
        contract["camera_ids"] = contract["camera_ids"][:2]
    elif change == "stale":
        bundle["started_at"] = (START - timedelta(days=31)).isoformat()
        bundle["ended_at"] = (END - timedelta(days=31)).isoformat()
    elif change == "future":
        bundle["ended_at"] = (NOW + timedelta(hours=1)).isoformat()
    elif change == "unsupported_ppe":
        contract["required_ppe"] = ["violence"]
    elif change == "missing_policy":
        del contract["policy"]["min_event_recall"]
    elif change == "zero_recall":
        contract["policy"]["min_event_recall"] = 0
    else:
        contract["policy"]["max_rpo_seconds"] = True
    update_contract(case)
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("stage,count", [("expansion", 50), ("factory", 200)])
def test_expansion_requires_previous_site_decision(case, stage, count):
    case[1].update(stage=stage, camera_ids=[str(uuid4()) for _ in range(count)])
    update_contract(case)
    assert evaluate(case)["status"] == "blocked"
    case[0]["previous_stage_signed_off"] = True
    case[0]["previous_stage_decision"] = save(case[2], "decision.json", {"test_fixture": True})
    assert evaluate(case)["status"] == "ready_for_site_review"


@pytest.mark.parametrize("gate,field,value", [
    ("model", "actual_device", "cpu"), ("model", "gpu_available", False),
    ("model", "model_sha256", "b" * 64), ("model", "created_at", (START - timedelta(seconds=1)).isoformat()),
    ("monitoring", "status", "fail"), ("monitoring", "active_targets", 1),
    ("monitoring", "checked_at", (END - timedelta(hours=2)).isoformat()),
])
def test_existing_machine_reports_must_match(case, gate, field, value):
    bundle, _, root = case
    report = json.loads((root / (gate + ".json")).read_text())
    report[field] = value
    bundle["gates"][gate]["evidence"] = [save(root, gate + ".json", report)]
    assert evaluate(case)["status"] == "blocked"


def test_changed_or_missing_attachment_blocks(case):
    path = case[2] / "restore.json"
    path.write_text("changed")
    assert evaluate(case)["status"] == "blocked"
    path.unlink()
    assert evaluate(case)["status"] == "blocked"


def test_inventory_must_match_frozen_contract_even_if_attachment_hash_is_updated(case):
    case[0]["release_evidence"]["hardware"] = save(case[2], "hardware-inventory.json", {"changed": True})
    assert evaluate(case)["status"] == "blocked"


@pytest.mark.parametrize("kind", ["absolute", "traversal", "symlink"])
def test_attachment_cannot_escape_bundle(case, kind, tmp_path):
    outside = tmp_path.parent / (str(uuid4()) + ".json")
    outside.write_text("secret-do-not-copy")
    try:
        name = str(outside) if kind == "absolute" else "../" + outside.name
        if kind == "symlink":
            (tmp_path / "escape.json").symlink_to(outside)
            name = "escape.json"
        case[0]["gates"]["restore"]["evidence"] = [{"path": name, "sha256": pilot.digest(outside.read_bytes())}]
        result = evaluate(case)
        assert result["status"] == "blocked"
        assert "secret-do-not-copy" not in json.dumps(result)
    finally:
        outside.unlink()


@pytest.mark.parametrize("content", ['{"status":"pass","status":"fail"}', '{"value":NaN}'])
def test_ambiguous_json_rejected(content):
    with pytest.raises(ValueError):
        pilot.strict_json(content)


def test_cli_unfilled_template_and_corrupt_json_block_without_overwriting(tmp_path):
    output = tmp_path / "result.json"
    command = [sys.executable, str(ROOT / "infra/pilot/acceptance.py"), "--bundle",
               str(ROOT / "infra/pilot/bundle.example.json"), "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(output.read_text())["status"] == "blocked"
    original = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == original
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"password":"secret-do-not-print",')
    command[-1] = str(tmp_path / "invalid-result.json")
    command[3] = str(invalid)
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2 and "secret-do-not-print" not in result.stdout + result.stderr
