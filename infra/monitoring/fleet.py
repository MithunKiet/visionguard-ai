"""Validated file discovery and live fleet coverage gate (no credential outputs)."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx

JOB = "visionguard-ai-worker"


def validate_inventory(data):
    if not isinstance(data, dict) or not isinstance(data.get("workers"), list) or not data["workers"]:
        raise ValueError("Inventory requires a nonempty workers list")
    tenants = data.get("enterprises", [])
    tenant_ids = set()
    for tenant in tenants:
        enterprise = str(UUID(tenant["enterprise_id"]))
        if enterprise in tenant_ids or not re.fullmatch(r"[A-Z][A-Z0-9_]*", tenant["token_env"]):
            raise ValueError("Duplicate enterprise or invalid credential variable name")
        tenant_ids.add(enterprise)
    identities, endpoints, business_ids = set(), set(), set()
    for worker in data["workers"]:
        enterprise, factory = str(UUID(worker["enterprise_id"])), str(UUID(worker["factory_id"]))
        worker_id = worker["worker_id"]
        if not isinstance(worker_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", worker_id):
            raise ValueError("Invalid worker ID")
        target = worker["target"]
        scheme = worker.get("scheme", "http")
        url = urlsplit(f"{scheme}://{target}")
        if (scheme not in {"http", "https"} or not url.hostname or not url.port or url.username
                or url.password or url.path or url.query or url.fragment or any(c.isspace() for c in target)):
            raise ValueError("Target must be a host:port without credentials or path")
        identity = (enterprise, worker_id)
        if enterprise not in tenant_ids or identity in identities or target in endpoints or worker_id in business_ids:
            raise ValueError("Unknown enterprise or duplicate worker/target")
        if enterprise != worker["enterprise_id"] or factory != worker["factory_id"]:
            raise ValueError("Use canonical UUIDs")
        identities.add(identity)
        endpoints.add(target)
        business_ids.add(worker_id)
    if tenant_ids != {w["enterprise_id"] for w in data["workers"]}:
        raise ValueError("Each enterprise must have at least one inventoried worker")
    return data


def targets_for(data):
    validate_inventory(data)
    return [{"targets": [w["target"]], "labels": {
        "worker_id": w["worker_id"], "enterprise_id": w["enterprise_id"], "factory_id": w["factory_id"],
        "__scheme__": w.get("scheme", "http"),
    }} for w in data["workers"]]


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".fleet-", delete=False) as file:
            name = file.name
            json.dump(data, file, indent=2, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, 0o644)  # Prometheus runs as an unprivileged container user.
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def coverage(data, registries, targets, samples, *, now=None):
    validate_inventory(data)
    now = time.time() if now is None else now
    expected = {(w["enterprise_id"], w["worker_id"]): w for w in data["workers"]}
    errors = []
    def problem(code, key):
        errors.append({"code": code, "enterprise_id": key[0], "worker_id": key[1]})
    registered = {}
    for tenant in data["enterprises"]:
        enterprise = tenant["enterprise_id"]
        if enterprise not in registries:
            problem("registry_unavailable", (enterprise, "*"))
            continue
        for worker in registries[enterprise]:
            key = (enterprise, worker["worker_id"])
            if worker["enterprise_id"] != enterprise or key in registered:
                problem("invalid_registry_identity", key)
            registered[key] = worker
            if key not in expected:
                problem("registered_worker_missing_from_inventory", key)
    active = [t for t in targets if t.get("labels", {}).get("job") == JOB]
    by_key = {}
    for target in active:
        labels = target["labels"]
        key = (labels.get("enterprise_id", ""), labels.get("worker_id", ""))
        by_key.setdefault(key, []).append(target)
        if key not in expected:
            problem("unexpected_prometheus_target", key)
    for key, worker in expected.items():
        registered_worker = registered.get(key)
        if registered_worker is None:
            problem("inventory_worker_not_registered", key)
        elif registered_worker.get("factory_id") != worker["factory_id"]:
            problem("factory_scope_mismatch", key)
        matches = by_key.get(key, [])
        if len(matches) != 1:
            problem("missing_or_duplicate_target", key)
            continue
        target = matches[0]
        expected_url = f"{worker.get('scheme', 'http')}://{worker['target']}/metrics"
        if target.get("scrapeUrl") != expected_url or target["labels"].get("factory_id") != worker["factory_id"]:
            problem("scrape_configuration_mismatch", key)
        try:
            scrape_age = now - datetime.fromisoformat(target["lastScrape"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError, TypeError):
            scrape_age = math.inf
        if target.get("health") != "up" or not 0 <= scrape_age <= 60:
            problem("target_down_or_stale", key)
        identities = [s for s in samples if s.get("metric", {}).get("job") == JOB
            and s["metric"].get("instance") == target["labels"].get("instance")]
        if len(identities) != 1:
            problem("missing_or_duplicate_runtime_identity", key)
            continue
        sample = identities[0]
        labels = sample["metric"]
        try:
            timestamp, value = sample["value"]
            valid_sample = 0 <= now - float(timestamp) <= 60 and float(value) == 1
        except (ValueError, TypeError, KeyError):
            valid_sample = False
        if (not valid_sample or labels.get("reported_worker_id") != key[1]
                or labels.get("reported_enterprise_id") != key[0]):
            problem("runtime_identity_mismatch_or_stale", key)
    return {"status": "pass" if not errors else "fail", "production_approved": False,
        "checked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "expected_workers": len(expected), "registered_workers": len(registered),
        "active_targets": len(active), "error_counts": dict(Counter(e["code"] for e in errors)), "errors": errors}


def origin(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Supply an origin without credentials, path or query")
    return value.rstrip("/")


def audit(data, backend, prometheus):
    registries = {}
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        for tenant in data["enterprises"]:
            token = os.environ.get(tenant["token_env"])
            if not token:
                raise ValueError("Missing administrator token environment variable")
            response = client.get(origin(backend) + "/api/v1/workers", headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            registries[tenant["enterprise_id"]] = response.json()["data"]
        response = client.get(origin(prometheus) + "/api/v1/targets", params={"state": "active"})
        response.raise_for_status()
        targets = response.json()
        response = client.get(origin(prometheus) + "/api/v1/query", params={"query": f'vg_worker_identity_info{{job="{JOB}"}}'})
        response.raise_for_status()
        identities = response.json()
        if targets.get("status") != "success" or identities.get("status") != "success" or identities["data"]["resultType"] != "vector":
            raise ValueError("Invalid Prometheus response")
    return coverage(data, registries, targets["data"]["activeTargets"], identities["data"]["result"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "audit"])
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend-url")
    parser.add_argument("--prometheus-url")
    args = parser.parse_args()
    try:
        data = validate_inventory(json.loads(Path(args.inventory).read_text()))
        result = targets_for(data) if args.action == "generate" else audit(data, args.backend_url, args.prometheus_url)
        atomic_json(args.output, result)
        print("Targets written" if args.action == "generate" else f"Fleet coverage: {result['status']}")
        return 0 if args.action == "generate" or result["status"] == "pass" else 1
    except Exception as error:
        # Do not echo HTTP URLs, tokens, inventory contents or exception bodies.
        if args.action == "audit":
            atomic_json(args.output, {"status": "error", "error_type": type(error).__name__, "production_approved": False})
        print(f"Fleet check failed: {type(error).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
