# VisionGuard AI

**Enterprise Factory Safety Monitoring Platform**

VisionGuard AI is a real-time computer vision platform that monitors factory floors for PPE compliance (helmets, vests), occupancy violations, and camera health — and alerts supervisors instantly via dashboard, email, and web push notifications.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Material UI, AG Grid |
| Backend | FastAPI, SQLAlchemy, Alembic, PostgreSQL |
| AI | OpenCV, RT-DETR, ByteTrack, PyTorch |
| Messaging | RabbitMQ (with Dead Letter Queue) |
| Cache | Redis |
| Storage | MinIO (S3-compatible) |
| Monitoring | Prometheus, Grafana, Loki |
| Deployment | Docker, Docker Compose |

---

## Architecture

```
React Dashboard
      │
      ▼
FastAPI Backend  ──────────────────────────────────────────┐
(JWT Auth, RBAC, WebSocket, Redis Cache, Rate Limiting)    │
      │                                                    │
      ▼                                                    │
RabbitMQ  ◄─────────────────────────────────────────────  │
(Events + Dead Letter Queue)                               │
      │                                                    │
      ▼                                                    │
AI Worker Pool                                             │
(RT-DETR + ByteTrack + OpenCV)                            │
      │                                                    │
      ▼                                                    │
RTSP Cameras  ─────────────────────────────────────────────┘
```

AI workers **never access the database directly** — they only publish events to RabbitMQ. The backend consumes events, writes to PostgreSQL, invalidates Redis cache, and pushes real-time updates to the dashboard via WebSocket.

Full architecture details → [`IMPLEMENTATION.md`](./IMPLEMENTATION.md)

---

## Features

- **PPE Detection** — helmet and vest compliance per zone, configurable confidence thresholds
- **Occupancy Monitoring** — real-time person count with zone-level max occupancy rules
- **Instant Alerts** — < 5 second latency from violation to supervisor notification
- **Real-Time Dashboard** — WebSocket-driven, no polling
- **Camera Health** — auto-detects offline cameras within 30 seconds, circuit breaker per camera
- **Snapshot Storage** — violation snapshots stored in MinIO, served via pre-signed URLs
- **Audit Trail** — every sensitive action logged immutably
- **Role Based Access** — Admin, Supervisor, Safety Officer, Viewer
- **Zone Config Hot-Swap** — change detection thresholds at runtime without restarting workers
- **Model Hot-Swap** — update AI models without restarting camera streams
- **Scales to 1000+ cameras** — horizontal scaling with no rewrite

---

## Project Structure

```
visionguard-ai/
│
├── backend/                        FastAPI modular monolith
│   └── src/
│       ├── main.py                 Entrypoint
│       ├── shared/                 Database, Redis, middleware, config
│       │   ├── database/
│       │   ├── cache/              Redis client + helpers
│       │   └── realtime/           WebSocket connection manager
│       └── modules/
│           ├── identity/           Auth, users, roles, JWT
│           ├── factory/            Factory management
│           ├── zone/               Zone management
│           ├── camera/             Camera registry
│           ├── occupancy/          Occupancy tracking
│           ├── ppe/                PPE violation records
│           ├── alerts/             Alert lifecycle
│           ├── notifications/      Email, in-app, web push
│           ├── analytics/          Trends, KPIs, reports
│           ├── config/             Zone-level config for workers
│           └── audit/              Immutable audit log
│
├── ai-worker/                      Python AI detection workers
│   └── src/
│       ├── main.py                 Entrypoint
│       ├── pipeline/               CameraWorker — detection loop
│       ├── events/                 RabbitMQ publisher
│       └── config/                 Settings + zone config sync
│
├── frontend/                       React + TypeScript
│   └── src/
│       ├── App.tsx
│       ├── pages/                  Dashboard, Alerts, Cameras, Analytics
│       └── components/             Layout, shared components
│
├── docker-compose.yml
├── .env.example
├── IMPLEMENTATION.md               Full architecture document
└── README.md
```

Each backend module follows Clean Architecture:

```
module/
├── api/            REST + WebSocket endpoints
├── application/    Use cases, command/query handlers
├── domain/         Entities, value objects, business rules
├── infrastructure/ DB repos, external services
└── contracts/      Shared interfaces
```

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Latest | Run all infrastructure |
| [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) | Latest | GPU support for AI workers |
| [Node.js](https://nodejs.org/) | 20+ | Frontend development |
| [Python](https://www.python.org/) | 3.11+ | Backend / AI worker local dev |

> Docker Desktop with WSL2 is required on Windows for GPU passthrough.

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/MithunKiet/visionguard-ai.git
cd visionguard-ai

cp .env.example .env
# Edit .env and fill in your values
```

### 2. Start infrastructure

```bash
docker compose up postgres rabbitmq redis minio -d
```

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

API docs (Swagger): `http://localhost:8000/docs`

### 4. Start AI worker (CPU mode for dev)

```bash
cd ai-worker
pip install -r requirements.txt

DEVICE=cpu python -m src.main
```

> For real cameras, add your RTSP URLs to the `CAMERAS` list in `ai-worker/src/config/settings.py`

### 5. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

---

## Start Everything with Docker

```bash
docker compose up --build
```

> GPU workers require NVIDIA Container Toolkit. CPU mode is used automatically if no GPU is detected.

---

## Environment Variables

Copy `.env.example` to `.env` and update:

| Variable | Description | Example |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password | `strongpassword` |
| `RABBITMQ_PASSWORD` | RabbitMQ password | `strongpassword` |
| `JWT_SECRET_KEY` | Long random string for JWT signing | `openssl rand -hex 32` |
| `REFRESH_TOKEN_SECRET` | Secret for refresh token signing | `openssl rand -hex 32` |
| `MINIO_ROOT_PASSWORD` | MinIO root password | `strongpassword` |
| `DEVICE` | AI inference device | `cuda` or `cpu` |
| `WORKER_ID` | Unique ID per worker instance | `worker-1` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |

---

## Default Credentials

| Service | URL | Username | Password |
|---|---|---|---|
| RabbitMQ | `http://localhost:15672` | `visionguard` | `visionguard123` |
| MinIO | `http://localhost:9001` | `visionguard` | `visionguard123` |

> Change all default credentials before deploying to production.

---

## RabbitMQ Events

AI workers publish these events:

| Event | Routing Key |
|---|---|
| Helmet missing | `events.helmet_missing_detected` |
| Vest missing | `events.vest_missing_detected` |
| Overcrowding | `events.overcrowding_detected` |
| Camera offline | `events.camera_offline_detected` |
| Camera reconnected | `events.camera_reconnected` |
| Occupancy update | `events.occupancy_updated` |
| Worker heartbeat | `events.worker_heartbeat` |

Failed events are routed to the Dead Letter Queue (DLQ) with automatic retry (3 attempts) before manual review.

---

## API Overview

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

GET    /api/v1/factories
GET    /api/v1/zones
GET    /api/v1/cameras
GET    /api/v1/alerts
PATCH  /api/v1/alerts/{id}/acknowledge
PATCH  /api/v1/alerts/{id}/resolve

GET    /api/v1/analytics/violations
GET    /api/v1/analytics/occupancy
GET    /api/v1/reports

GET    /api/v1/config/zone/{zone_id}
PUT    /api/v1/config/zone/{zone_id}

GET    /api/v1/audit

WS     /ws/dashboard
WS     /ws/alerts
```

Full API docs available at `http://localhost:8000/docs` when backend is running.

---

## Roles & Permissions

| Role | Alerts | Cameras | Config | Users | Audit |
|---|---|---|---|---|---|
| Admin | Full | Full | Full | Full | Full |
| Supervisor | Acknowledge, Resolve | View | — | — | — |
| Safety Officer | View | View | — | — | — |
| Viewer | View | View | — | — | — |

---

## Snapshot Storage

Violation snapshots are stored in MinIO under:

```
snapshots/{zone_id}/{camera_id}/{timestamp}.jpg
```

The backend serves time-limited pre-signed URLs to the frontend. Snapshots are never served directly from disk.

Retention:

| Storage | Duration |
|---|---|
| Online (MinIO) | 90 days |
| Cold archive | 1 year |
| Purged | After 1 year |

---

## Monitoring

Start Prometheus + Grafana:

```bash
docker compose up prometheus grafana loki -d
```

| Service | URL |
|---|---|
| Grafana | `http://localhost:3000` |
| Prometheus | `http://localhost:9090` |

Pre-built dashboards:

- System Overview (API health, latency, error rate)
- AI Worker Health (inference latency, frame rate, queue depth)
- Alert Operations (volume, resolution time, open alerts by zone)
- Camera Health (online/offline, reconnection rate)
- DLQ Monitor (failed event depth over time)

---

## Scaling

| Cameras | Backend | AI Workers |
|---|---|---|
| 100 | 1 server | 4 GPU workers |
| 200 | 2 servers | 8 GPU workers |
| 500 | 3–5 node cluster | 20+ GPU workers |
| 1000+ | API Gateway + cluster | 50+ workers + Kubernetes |

No rewrite required — horizontal scaling only.

---

## License

MIT License — see [LICENSE](./LICENSE) for details.

All dependencies are open source. See [`IMPLEMENTATION.md`](./IMPLEMENTATION.md) for license details per component.
