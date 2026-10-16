"""Validate the merged production Compose configuration without starting services."""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
env = {**os.environ, "VITE_WS_URL": "wss://test.invalid", "CAMERA_ALLOWED_HOSTS": '["camera.test.invalid"]',
       "PPE_MODEL_SHA256": "0" * 64, "FLEET_TARGETS_DIR": str(root / "capacity-data/prometheus-targets"),
       "WORKER_CREDENTIALS": '{"worker-1":{"key":"test-only","enterprise_id":"test-only"}}',
       "WORKER_1_GPU_DEVICE_ID": "0", "WORKER_2_GPU_DEVICE_ID": "1", "MEDIA_HLS_SECRET": "test-only", "MEDIAMTX_PUBLISH_PASSWORD": "test-only", "WORKER_1_API_KEY": "test-only", "WORKER_2_API_KEY": "test-only"}
result = subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml",
                         "config", "--format", "json"], cwd=root, env=env, check=True, capture_output=True, text=True)
services = json.loads(result.stdout)["services"]
for name, service in services.items():
    if name == "frontend":
        ports = service.get("ports", [])
        assert len(ports) == 1 and ports[0]["host_ip"] == "127.0.0.1" and ports[0]["target"] == 80
    else:
        assert not service.get("ports"), f"Unexpected published port on {name}"
for name in ("backend", "frontend"):
    assert not services[name].get("volumes"), f"Unexpected development mount on {name}"
assert services["backend"]["environment"]["MEDIA_HLS_URL"] == "http://mediamtx:8888"
assert services["backend"]["environment"]["MEDIA_HLS_SECRET"] == services["mediamtx"]["environment"]["MTX_HLSCDNSECRET"]
assert "VITE_MEDIAMTX_WEBRTC_URL" not in services["frontend"]["build"].get("args", {})
assert services["backend"]["command"] == ["sh", "scripts/start.sh"]
assert services["frontend"]["build"]["dockerfile"] == "frontend/Dockerfile.prod"
print("Production Compose checks passed: private services, no development mounts, migration startup enabled.")

for name in ("ai-worker", "ai-worker-2"):
    mounts = services[name].get("volumes", [])
    assert len(mounts) == 2
    models = next(m for m in mounts if m["target"] == "/app/models")
    state = next(m for m in mounts if m["target"] == "/app/state")
    assert models["read_only"] and state["type"] == "volume" and not state.get("read_only")
    assert services[name]["environment"]["EDGE_STATE_DIR"] == "/app/state"
    assert int(services[name]["shm_size"]) > 0
    assert int(services[name]["environment"]["CAPTURE_MAX_FRAME_BYTES"]) > 0
    assert float(services[name]["environment"]["FRAME_MAX_AGE_SECONDS"]) > 0
    assert services[name]["environment"]["USE_GPU"] == "true"
    assert services[name]["environment"]["ENVIRONMENT"] == "production"
    assert services[name]["environment"]["DEMO_MODE"] == "false"
    assert services[name]["environment"]["YOLO_MODEL_SHA256"] == "0" * 64
    devices = services[name]["deploy"]["resources"]["reservations"]["devices"]
    assert len(devices) == 1 and devices[0]["device_ids"] and "count" not in devices[0]
assert services["ai-worker"]["volumes"][1]["source"] != services["ai-worker-2"]["volumes"][1]["source"]
print("Worker checks passed: read-only models, separate persistent journals and explicit GPU allocation.")

monitoring = services["prometheus"]["volumes"]
assert any(v["target"] == "/etc/prometheus/targets" and v.get("read_only") and v["source"].endswith("capacity-data/prometheus-targets") for v in monitoring)
print("Fleet monitoring checks passed: explicit private target directory required.")
