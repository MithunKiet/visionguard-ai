"""Fleet coverage must fail for missing, mislabeled and stale workers."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location("fleet", Path(__file__).resolve().parents[2] / "infra/monitoring/fleet.py")
fleet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)
NOW = 1000000000


def fixture():
    enterprise, factory = str(uuid4()), str(uuid4())
    worker = {"worker_id": "worker-1", "enterprise_id": enterprise, "factory_id": factory, "target": "edge-a:8001"}
    inventory = {"enterprises": [{"enterprise_id": enterprise, "token_env": "FLEET_TOKEN"}], "workers": [worker]}
    registry = {enterprise: [{k: worker[k] for k in ("worker_id", "enterprise_id", "factory_id")}]}
    target = {"labels": {"job": fleet.JOB, "instance": worker["target"], **registry[enterprise][0]},
        "scrapeUrl": "http://edge-a:8001/metrics", "health": "up", "lastScrape": datetime.fromtimestamp(NOW, timezone.utc).isoformat()}
    sample = {"metric": {"job": fleet.JOB, "instance": worker["target"], "reported_worker_id": worker["worker_id"],
        "reported_enterprise_id": enterprise}, "value": [NOW, "1"]}
    return inventory, registry, [target], [sample]


def test_complete_coverage_and_generated_targets_do_not_export_token_names():
    data, registry, targets, samples = fixture()
    assert fleet.coverage(data, registry, targets, samples, now=NOW)["status"] == "pass"
    generated = fleet.targets_for(data)
    assert generated[0]["labels"]["factory_id"] == data["workers"][0]["factory_id"]
    assert "token" not in json.dumps(generated).lower()


@pytest.mark.parametrize("issue", ["missing_target", "duplicate_target", "down", "stale_scrape", "wrong_endpoint",
    "missing_identity", "wrong_identity", "wrong_tenant_identity", "stale_identity", "wrong_factory", "unregistered", "unmonitored", "registry_unavailable"])
def test_coverage_failures(issue):
    data, registry, targets, samples = fixture()
    enterprise = data["workers"][0]["enterprise_id"]
    if issue == "missing_target":
        targets.clear()
    elif issue == "duplicate_target":
        targets.append(deepcopy(targets[0]))
    elif issue == "down":
        targets[0]["health"] = "down"
    elif issue == "stale_scrape":
        targets[0]["lastScrape"] = datetime.fromtimestamp(NOW - 61, timezone.utc).isoformat()
    elif issue == "wrong_endpoint":
        targets[0]["scrapeUrl"] = "http://wrong:8001/metrics"
    elif issue == "missing_identity":
        samples.clear()
    elif issue == "wrong_identity":
        samples[0]["metric"]["reported_worker_id"] = "wrong"
    elif issue == "wrong_tenant_identity":
        samples[0]["metric"]["reported_enterprise_id"] = str(uuid4())
    elif issue == "stale_identity":
        samples[0]["value"][0] = NOW - 61
    elif issue == "wrong_factory":
        registry[enterprise][0]["factory_id"] = str(uuid4())
    elif issue == "unregistered":
        registry[enterprise].clear()
    elif issue == "registry_unavailable":
        registry.clear()
    else:
        registry[enterprise].append({**registry[enterprise][0], "worker_id": "new-worker"})
    result = fleet.coverage(data, registry, targets, samples, now=NOW)
    assert result["status"] == "fail" and result["errors"]
    assert result["production_approved"] is False


@pytest.mark.parametrize("target", ["http://host:8001", "user:secret@host:8001", "host:8001/path", "host:8001?token=x",
    "host", "host:0", "host:99999", "host:8001#x", "host:8001\n"])
def test_invalid_targets_are_not_written(target):
    data, *_ = fixture()
    data["workers"][0]["target"] = target
    with pytest.raises(ValueError):
        fleet.targets_for(data)


@pytest.mark.parametrize("duplicate", ["worker", "target"])
def test_duplicate_workers_or_endpoints_cannot_hide_missing_coverage(duplicate):
    data, *_ = fixture()
    worker = deepcopy(data["workers"][0])
    worker["worker_id" if duplicate == "target" else "target"] = "different" if duplicate == "target" else "different:8001"
    data["workers"].append(worker)
    with pytest.raises(ValueError):
        fleet.targets_for(data)


def test_atomic_generation_preserves_previous_file_when_validation_fails(tmp_path):
    path = tmp_path / "workers.json"
    data, *_ = fixture()
    fleet.atomic_json(path, fleet.targets_for(data))
    original = path.read_bytes()
    data["workers"][0]["target"] = "secret@host:123"
    with pytest.raises(ValueError):
        fleet.atomic_json(path, fleet.targets_for(data))
    assert path.read_bytes() == original


def test_unfilled_example_is_not_deployable():
    example = Path(__file__).resolve().parents[2] / "infra/monitoring/fleet.example.json"
    with pytest.raises(ValueError):
        fleet.validate_inventory(json.loads(example.read_text()))


@pytest.mark.skipif(not __import__("os").environ.get("TEST_FLEET_PROMETHEUS_URL"), reason="Requires isolated Prometheus file discovery")
def test_real_prometheus_discovers_atomic_target_additions(tmp_path):
    import os
    import time
    import httpx
    from prometheus_client import CollectorRegistry, Gauge, start_http_server
    base = os.environ["TEST_FLEET_PROMETHEUS_URL"]
    target_dir = Path(os.environ["TEST_FLEET_TARGETS_DIR"])
    data, registry, _, _ = fixture()
    def fetch(client, path, **kwargs):
        response = client.get(base + path, **kwargs)
        response.raise_for_status()
        return response.json()
    server_list = []
    try:
        for index in range(2):
            worker = deepcopy(data["workers"][0])
            worker["worker_id"] = f"worker-{index + 1}"
            metrics = CollectorRegistry()
            Gauge("vg_worker_identity_info", "Test runtime identity", ["reported_worker_id", "reported_enterprise_id"], registry=metrics).labels(
                worker["worker_id"], worker["enterprise_id"]).set(1)
            server, thread = start_http_server(0, addr="127.0.0.1", registry=metrics)
            server_list.append((server, thread))
            worker["target"] = f"127.0.0.1:{server.server_port}"
            if index == 0:
                data["workers"][0] = worker
            else:
                data["workers"].append(worker)
                registry[worker["enterprise_id"]].append({k: worker[k] for k in ("worker_id", "enterprise_id", "factory_id")})
            fleet.atomic_json(target_dir / "workers.json", fleet.targets_for(data))
            result = None
            deadline = time.monotonic() + 30
            with httpx.Client(timeout=5) as client:
                while time.monotonic() < deadline:
                    try:
                        targets = fetch(client, "/api/v1/targets")["data"]["activeTargets"]
                        samples = fetch(client, "/api/v1/query", params={"query": "vg_worker_identity_info"})["data"]["result"]
                        result = fleet.coverage(data, registry, targets, samples)
                    except httpx.HTTPError:
                        result = {"status": "starting"}
                    if result["status"] == "pass":
                        break
                    time.sleep(.5)
            assert result["status"] == "pass", result
        # A stale configuration cannot hide a missing inventory member.
        fleet.atomic_json(target_dir / "workers.json", fleet.targets_for({**data, "workers": data["workers"][:1]}))
        deadline = time.monotonic() + 30
        with httpx.Client(timeout=5) as client:
            while time.monotonic() < deadline:
                targets = client.get(base + "/api/v1/targets").json()["data"]["activeTargets"]
                if len(targets) == 1:
                    break
                time.sleep(.5)
        assert fleet.coverage(data, registry, targets, samples)["status"] == "fail"
    finally:
        for server, thread in server_list:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_audit_sends_jwt_only_to_backend_and_refuses_redirects(monkeypatch):
    import httpx
    data, registry, targets, samples = fixture()
    monkeypatch.setenv("FLEET_TOKEN", "test-secret")
    client_class = httpx.Client
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.host == "backend.test":
            assert request.headers["authorization"] == "Bearer test-secret"
            return httpx.Response(200, json={"data": registry[data["workers"][0]["enterprise_id"]]})
        assert "authorization" not in request.headers
        if request.url.path.endswith("targets"):
            return httpx.Response(200, json={"status": "success", "data": {"activeTargets": targets}})
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": samples}})
    monkeypatch.setattr(fleet.httpx, "Client", lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(fleet.time, "time", lambda: NOW)
    assert fleet.audit(data, "https://backend.test", "http://prometheus.test")["status"] == "pass"
    assert len(requests) == 3
    def redirect(request):
        return httpx.Response(302, headers={"Location": "https://untrusted.test"})
    monkeypatch.setattr(fleet.httpx, "Client", lambda **kwargs: client_class(transport=httpx.MockTransport(redirect), **kwargs))
    with pytest.raises(httpx.HTTPStatusError):
        fleet.audit(data, "https://backend.test", "http://prometheus.test")
