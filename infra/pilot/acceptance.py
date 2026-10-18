"""Check a factory pilot evidence bundle; never authorize production or contact a site."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import UUID


STAGES = {"pilot": (10, 20), "expansion": (50, 100), "factory": (200, 200)}
# Boolean checks are reviewer attestations, not automatically measured facts.
CHECKS = {
    "deployment": ("inventory_verified", "licenses_reviewed", "production_config_verified", "image_scan_reviewed"),
    "model": ("target_gpu_image_verified",),
    "accuracy": ("independent_labels_reviewed", "all_class_condition_cells_reviewed", "event_pipeline_evaluated"),
    "camera_dvr": ("dvr_recording_uninterrupted", "source_freshness_measured", "placement_verified"),
    "capacity": ("every_camera_meets_fps", "whole_process_tree_measured", "spare_capacity_tested", "shared_services_measured"),
    "soak": ("representative_shifts_covered", "continuous_observation_verified"),
    "failover": ("worker_loss_tested", "gpu_hang_tested", "api_partition_tested", "camera_reconnect_tested", "fencing_verified"),
    "delivery": ("broker_outage_replay_tested", "storage_outage_replay_tested", "provider_receipts_verified"),
    "monitoring": ("coverage_audit_scheduled", "operations_page_received", "host_gpu_disk_broker_outbox_monitored"),
    "restore": ("isolated_restore_verified", "database_objects_reconciled", "worker_state_replay_verified", "broker_loss_accounted", "offsite_backup_verified"),
    "security": ("tenant_isolation_tested", "https_media_access_tested", "secrets_and_private_network_verified"),
    "rollback": ("rollback_rehearsed", "response_owner_assigned", "open_blocking_defects_zero"),
}
# op, fixed target or contract policy key. Targets in the contract must be agreed before testing.
METRICS = {
    "accuracy": {"minimum_event_precision": ("min", "min_event_precision"),
                 "minimum_event_recall": ("min", "min_event_recall"),
                 "maximum_false_alerts_per_camera_hour": ("max", "max_false_alerts_per_camera_hour"),
                 "minimum_positive_episodes_per_cell": ("min", "min_positive_episodes_per_cell"),
                 "minimum_negative_camera_hours_per_cell": ("min", "min_negative_camera_hours_per_cell")},
    "capacity": {"capture_to_alert_p95_seconds": ("max", "max_capture_to_alert_p95_seconds"),
                 "peak_cpu_fraction": ("max", 0.85), "peak_ram_fraction": ("max", 0.85),
                 "peak_gpu_memory_fraction": ("max", 0.85)},
    "soak": {"continuous_hours": ("min", 24), "lost_events": ("max", 0),
             "stale_frame_events": ("max", 0), "inference_errors": ("max", 0),
             "rejected_edge_events": ("max", 0), "unexplained_duplicate_events": ("max", 0)},
    "failover": {"worst_recovery_seconds": ("max", "max_failover_seconds"), "overlapping_authorized_owners": ("max", 0)},
    "delivery": {"lost_events": ("max", 0), "failed_notifications": ("max", 0), "pending_at_drain_end": ("max", 0)},
    "restore": {"recovery_seconds": ("max", "max_restore_seconds"), "data_loss_seconds": ("max", "max_rpo_seconds"),
                "unaccounted_events": ("max", 0), "missing_referenced_objects": ("max", 0)},
}
POLICIES = {value for metrics in METRICS.values() for _, value in metrics.values() if isinstance(value, str)}
PPE = {"helmet", "vest", "gloves", "safety_shoes"}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def valid_hash(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone is required")
    return result.astimezone(timezone.utc)


def identifier(value):
    return isinstance(value, str) and str(UUID(value)) == value


def named(value):
    return isinstance(value, str) and bool(value.strip())


def strict_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Nonfinite JSON number")
    return json.loads(content, object_pairs_hook=pairs, parse_constant=constant)


def attachment(root, ref):
    """No URLs, absolute paths, traversal or symlink escapes; never copy source content to output."""
    path = Path(ref["path"])
    if path.is_absolute() or ".." in path.parts or not valid_hash(ref.get("sha256")):
        raise ValueError("Invalid attachment reference")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Attachment must be inside the bundle")
    if resolved.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Attach a bounded report, not footage")
    content = resolved.read_bytes()
    if digest(content) != ref["sha256"]:
        raise ValueError("Attachment checksum mismatch")
    return content


def evaluate(bundle, root, now=None):
    now = now or datetime.now(timezone.utc)
    errors = []
    result = {"status": "blocked", "production_approved": False, "evidence_independently_verified": False,
              "created_at": now.isoformat(), "blocking_reasons": errors}
    try:
        if type(bundle["schema_version"]) is not int or bundle["schema_version"] != 1 or bundle["scope"] != "real_factory_pilot":
            raise ValueError("Invalid bundle version or scope")
        contract_bytes = attachment(root, bundle["contract"])
        contract = strict_json(contract_bytes)
        result["contract_sha256"] = digest(contract_bytes)
        stage = contract["stage"]
        minimum, maximum = STAGES[stage]
        cameras = contract["camera_ids"]
        if (not isinstance(cameras, list) or not minimum <= len(cameras) <= maximum
                or not all(identifier(camera) for camera in cameras) or len(set(cameras)) != len(cameras)):
            raise ValueError("Invalid stage camera inventory")
        if not all(identifier(contract[key]) for key in ("enterprise_id", "factory_id")):
            raise ValueError("Invalid site identifiers")
        release = contract["release"]
        if not valid_hash(release["git_commit"], 40) or not all(valid_hash(release[key]) for key in
                ("model_sha256", "images_sha256", "hardware_sha256", "configuration_sha256")):
            raise ValueError("Pin release, model, images, hardware and configuration")
        started, ended = timestamp(bundle["started_at"]), timestamp(bundle["ended_at"])
        if not started < ended <= now or (now - ended).total_seconds() > 30 * 86400:
            raise ValueError("Invalid or stale observation window")
        if (not named(contract["approved_by"]) or timestamp(contract["approved_at"]) > started
                or not named(contract["site_owner"])):
            raise ValueError("Agree the contract before observation")
        if (not isinstance(contract["required_ppe"], list) or not contract["required_ppe"]
                or not set(contract["required_ppe"]) <= PPE
                or len(set(contract["required_ppe"])) != len(contract["required_ppe"])
                or not isinstance(contract["conditions"], list) or not contract["conditions"]
                or not all(named(value) for value in contract["conditions"])
                or len(set(contract["conditions"])) != len(contract["conditions"])):
            raise ValueError("Identify supported PPE and representative conditions")
        policy = contract["policy"]
        for key in POLICIES:
            value = policy[key]
            if not number(value) or (key not in {"max_false_alerts_per_camera_hour", "max_rpo_seconds"} and value == 0):
                raise ValueError("Acceptance targets must be explicit finite numbers")
            if key in {"min_event_precision", "min_event_recall"} and value > 1:
                raise ValueError("Precision and recall targets must be fractions")
        if type(policy["min_positive_episodes_per_cell"]) is not int:
            raise ValueError("Episode count must be an integer")
        if stage != "pilot" and bundle.get("previous_stage_signed_off") is not True:
            errors.append("previous_stage: signed site decision required")
        if stage != "pilot":
            attachment(root, bundle["previous_stage_decision"])
        result.update(stage=stage, camera_count=len(cameras))
    except (KeyError, TypeError, ValueError, AttributeError, OSError):
        errors.append("contract: missing, invalid, stale or unverified; check the template and attached contract")
        return result

    for gate, checks in CHECKS.items():
        try:
            row = bundle["gates"][gate]
            if (row["status"] != "pass" or not named(row["reviewer"]) or not named(row["summary"])
                    or not started <= timestamp(row["observed_at"]) <= ended
                    or row["contract_sha256"] != result["contract_sha256"]):
                raise ValueError("Missing review or inconsistent observation scope")
            refs = row["evidence"]
            if not isinstance(refs, list) or not refs:
                raise ValueError("Evidence missing")
            contents = [attachment(root, ref) for ref in refs]
            if gate == "deployment":
                for key in ("images", "hardware", "configuration"):
                    content = attachment(root, bundle["release_evidence"][key])
                    if digest(content) != release[key + "_sha256"]:
                        errors.append(f"deployment: {key} inventory differs from the agreed contract")
            for key in checks:
                if row["checks"].get(key) is not True:
                    errors.append(f"{gate}: {key} is not verified")
            for key, (op, target) in METRICS.get(gate, {}).items():
                value = row["measurements"].get(key)
                target = policy[target] if isinstance(target, str) else target
                if not number(value) or (value < target if op == "min" else value > target):
                    errors.append(f"{gate}: {key} missing or outside the agreed limit")
                elif ("precision" in key or "recall" in key or "fraction" in key) and value > 1:
                    errors.append(f"{gate}: {key} must be a fraction")
                elif key == "minimum_positive_episodes_per_cell" and type(value) is not int:
                    errors.append(f"{gate}: {key} must be an integer")
            if gate == "soak" and number(row["measurements"].get("continuous_hours")):
                if row["measurements"]["continuous_hours"] > (ended - started).total_seconds() / 3600:
                    errors.append("soak: claimed duration exceeds observation window")
            # The first attachment has a defined machine-readable contract for these gates.
            if gate == "model":
                report = strict_json(contents[0])
                if (report["status"] != "model_ready" or report["scope"] != "startup_smoke"
                        or report["gpu_available"] is not True or report["actual_device"] != "cuda:0"
                        or report["model_sha256"] != release["model_sha256"]
                        or not started <= timestamp(report["created_at"]) <= ended):
                    errors.append("model: target CUDA readiness report does not match this run")
            if gate == "monitoring":
                report = strict_json(contents[0])
                if (report["status"] != "pass" or report["errors"] or report["error_counts"]
                        or type(report["expected_workers"]) is not int or report["expected_workers"] < 1
                        or not report["expected_workers"] == report["registered_workers"] == report["active_targets"]
                        or not 0 <= (ended - timestamp(report["checked_at"])).total_seconds() <= 3600):
                    errors.append("monitoring: successful coverage report within the final hour is required")
        except (KeyError, TypeError, ValueError, AttributeError, OSError):
            errors.append(f"{gate}: missing, invalid, failed or checksum-mismatched evidence")
    if not errors:
        result["status"] = "ready_for_site_review"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path; existing evidence is never overwritten")
    try:
        content = args.bundle.read_bytes()
        report = evaluate(strict_json(content), args.bundle.parent)
        report["bundle_sha256"] = digest(content)
    except (ValueError, TypeError, OSError):
        report = {"status": "blocked", "production_approved": False, "evidence_independently_verified": False,
                  "blocking_reasons": ["bundle: unreadable or invalid JSON"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(report["status"])
    for reason in report["blocking_reasons"]:
        print(f"- {reason}")
    return 0 if report["status"] == "ready_for_site_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
