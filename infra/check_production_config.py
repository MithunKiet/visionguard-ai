"""Validate the merged production Compose configuration without starting services."""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
env = {**os.environ, "VITE_WS_URL": "wss://test.invalid", "CAMERA_ALLOWED_HOSTS": '["camera.test.invalid"]',
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
    assert len(mounts) == 1 and mounts[0]["target"] == "/app/models" and mounts[0]["read_only"]
    devices = services[name]["deploy"]["resources"]["reservations"]["devices"]
    assert len(devices) == 1 and devices[0]["device_ids"] and "count" not in devices[0]
print("Worker checks passed: read-only model mounts and explicit GPU allocation.")
