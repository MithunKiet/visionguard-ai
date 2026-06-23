# VisionGuard AI

Enterprise Factory Safety Monitoring Platform

---

## Prerequisites

Make sure these are installed:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with WSL2 on Windows)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for GPU support)
- [Node.js 20+](https://nodejs.org/) (for frontend)
- [Python 3.11+](https://www.python.org/) (for local dev without Docker)

---

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd visionguard

# Copy env file and fill in your values
cp .env.example .env
```

### 2. Start infrastructure

```bash
docker compose up postgres rabbitmq redis minio -d
```

Services available at:

| Service | URL |
|---|---|
| PostgreSQL | `localhost:5432` |
| RabbitMQ Management | `http://localhost:15672` |
| MinIO Console | `http://localhost:9001` |
| Redis | `localhost:6379` |

### 3. Start backend

```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 4. Start AI worker (CPU mode for dev)

```bash
cd ai-worker
pip install -r requirements.txt

# For CPU-only testing (no camera needed)
DEVICE=cpu python -m src.main
```

> For real cameras, update the `CAMERAS` list in `ai-worker/src/main.py` with your RTSP URLs.

### 5. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

---

## Start everything with Docker

```bash
docker compose up --build
```

> GPU workers require NVIDIA Container Toolkit. On Windows, make sure WSL2 is configured with GPU passthrough.

---

## Project Structure

```
visionguard/
├── backend/              FastAPI modular monolith
│   └── src/
│       ├── main.py       Entrypoint
│       ├── shared/       Database, middleware, config
│       └── modules/      identity, factory, zone, camera,
│                         occupancy, ppe, alerts, notifications,
│                         analytics, reports, config, audit
│
├── ai-worker/            Python AI detection workers
│   └── src/
│       ├── main.py       Entrypoint
│       ├── pipeline/     CameraWorker — detection loop
│       ├── events/       RabbitMQ publisher
│       └── config/       Settings
│
├── frontend/             React + TypeScript + Material UI
│   └── src/
│       ├── App.tsx
│       ├── pages/        Dashboard, Alerts, Cameras, Analytics
│       └── components/   Layout, shared components
│
├── docker-compose.yml
├── .env.example
└── IMPLEMENTATION.md
```

---

## Environment Variables

Copy `.env.example` to `.env` and update:

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Database password |
| `RABBITMQ_PASSWORD` | RabbitMQ password |
| `JWT_SECRET_KEY` | Long random string for JWT signing |
| `DEVICE` | `cuda` for GPU, `cpu` for testing |
| `WORKER_ID` | Unique ID per worker instance |

---

## RabbitMQ

Management UI: `http://localhost:15672`  
Default login: `visionguard` / `visionguard123`

Events published by workers:

| Event | Routing Key |
|---|---|
| Helmet missing | `events.helmet_missing_detected` |
| Vest missing | `events.vest_missing_detected` |
| Overcrowding | `events.overcrowding_detected` |
| Camera offline | `events.camera_offline_detected` |
| Occupancy update | `events.occupancy_updated` |

---

## MinIO

Console: `http://localhost:9001`  
Default login: `visionguard` / `visionguard123`

Violation snapshots are stored under:

```
snapshots/{zone_id}/{camera_id}/{timestamp}.jpg
```

---

## Next Steps

- [ ] Implement JWT auth in identity module
- [ ] Wire backend RabbitMQ consumer to process AI events
- [ ] Implement actual RT-DETR inference in `ai-worker/src/pipeline/camera_worker.py`
- [ ] Implement MinIO snapshot upload in `_save_snapshot()`
- [ ] Add Alembic migrations
- [ ] Build React dashboard pages
- [ ] Add Prometheus + Grafana monitoring
