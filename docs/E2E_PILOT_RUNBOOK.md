# VisionGuard AI — E2E Pilot Runbook

Full chain: RTSP test stream -> AI Worker detection -> RabbitMQ -> Backend -> WebSocket -> Frontend dashboard.

## 0. One-time setup

```bash
cp backend/.env.example backend/.env
# edit backend/.env: set MASTER_PASSWORD_HASH (optional) and WORKER_API_KEY (any string, must match ai-worker)
```

`docker-compose.yml` reads `WORKER_API_KEY` from the shell/`.env` at the repo root for both `backend` and `ai-worker` — set it once there so both sides match:

```bash
echo "WORKER_API_KEY=dev-worker-key-change-me" >> .env
```

If you don't have an NVIDIA GPU, edit `docker-compose.yml` and remove the `deploy.resources.reservations.devices` block under `ai-worker`, and set `USE_GPU: "false"`.

## 1. Bring up infrastructure

```bash
docker compose up -d postgres redis rabbitmq minio mediamtx
docker compose ps   # wait for postgres/redis/rabbitmq/minio to show healthy
```

## 2. Push a looping test video into the RTSP simulator

Any local MP4 works (a factory floor / person walking clip is ideal). Requires `ffmpeg` on the host:

```bash
ffmpeg -re -stream_loop -1 -i sample.mp4 -c copy -f rtsp rtsp://localhost:8554/factory-cam-01
```

Leave this running in its own terminal.

## 3. Migrate + seed

```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m scripts.seed_super_admin
docker compose run --rm backend python -m scripts.seed_demo_pilot
```

`seed_demo_pilot` creates a Factory/Department/Zone/ZoneConfig, pre-registers `AIWorker` row `worker-1`, and creates `Camera CAM1` pointed at `rtsp://mediamtx:8554/factory-cam-01`, assigned to that worker. Copy the printed **Enterprise ID** — you'll need it for the AI Worker.

```bash
# repo-root .env
echo "SEED_ENTERPRISE_ID=<paste-enterprise-id-here>" >> .env
```

## 4. Start the backend

```bash
docker compose up -d backend
docker compose logs -f backend
# wait for "Application startup complete" and "rabbitmq.consumer" listening
```

## 5. Start the AI Worker

```bash
docker compose up -d ai-worker
docker compose logs -f ai-worker
```

Expected log sequence: `ai_worker.starting` -> `detector.loading` -> `ai_worker.cameras_loaded count=1` -> `camera_worker.started`.

**Note:** unless you've placed a fine-tuned PPE model at `ai-worker/models/yolov8s-ppe.pt`, the detector falls back to a generic pretrained YOLOv8 model (`detector.ppe_model_missing` log line) — it will detect people but won't emit real helmet/vest/etc. violations. To see the full alert pipeline without a real PPE model, publish a synthetic event instead:

```bash
docker compose exec backend python -m scripts.publish_test_violation \
  --enterprise-id <enterprise-id> --factory-id <factory-id> --zone-id <zone-id> --camera-id <camera-id> \
  --type helmet_missing --confidence 0.87
```

(Get factory/zone/camera ids from `GET /api/v1/cameras` in Swagger, or from the `seed_demo_pilot` output.)

## 6. Start the frontend

```bash
docker compose up -d frontend
```

Open [http://localhost:5173](http://localhost:5173), log in with the seeded SUPER_ADMIN (`admin@visionguard.ai` / the password printed by `seed_super_admin`).

- **Cameras** page should show `CAM1` as `Active`.
- **Dashboard** live feed panel should show a `violation.created` and `alert.created` event within seconds of running the test publisher (or a real detection).
- **Alerts** page: acknowledge -> resolve the alert and confirm the status updates without a page reload.

## Troubleshooting

- `401` from `/workers/heartbeat` or `/workers/{id}/cameras`: `WORKER_API_KEY` mismatch between backend and ai-worker, or missing `ENTERPRISE_ID` on the ai-worker container.
- WebSocket never connects: check the browser console for the `/api/v1/ws/live?token=...` handshake — the JWT must not be expired; log out/in to refresh.
- No violations ever appear: expected if using the fallback YOLO model — use `publish_test_violation.py` to demo the pipeline instead.
