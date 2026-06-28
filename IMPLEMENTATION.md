# IMPLEMENTATION.md

# VisionGuard AI
## Enterprise Factory Safety Monitoring & Compliance Platform

---

# Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [High Level System Architecture](#2-high-level-system-architecture)
3. [Physical Architecture](#3-physical-architecture)
4. [Modular Monolith — Module Breakdown](#4-modular-monolith--module-breakdown)
5. [Clean Architecture — Per Module Structure](#5-clean-architecture--per-module-structure)
6. [Authentication & Authorization](#6-authentication--authorization)
7. [Event Driven Architecture](#7-event-driven-architecture)
8. [AI Worker Architecture](#8-ai-worker-architecture)
9. [Rules Engine](#9-rules-engine)
10. [WebSocket & Real-Time Architecture](#10-websocket--real-time-architecture)
11. [API Design & Versioning](#11-api-design--versioning)
12. [Caching Strategy](#12-caching-strategy)
13. [Database Architecture](#13-database-architecture)
14. [Snapshot Storage Architecture](#14-snapshot-storage-architecture)
15. [Data Retention Policy](#15-data-retention-policy)
16. [Dashboard Architecture](#16-dashboard-architecture)
17. [Analytics Architecture](#17-analytics-architecture)
18. [Notification Architecture](#18-notification-architecture)
19. [Zone Configuration Flow](#19-zone-configuration-flow)
20. [API Rate Limiting](#20-api-rate-limiting)
21. [Security Architecture](#21-security-architecture)
22. [Monitoring & Observability](#22-monitoring--observability)
23. [Audit Trail](#23-audit-trail)
24. [Logging Strategy](#24-logging-strategy)
25. [Testing Strategy](#25-testing-strategy)
26. [CI/CD Pipeline](#26-cicd-pipeline)
27. [Deployment Architecture](#27-deployment-architecture)
28. [Scaling Strategy](#28-scaling-strategy)
29. [Future Integrations](#29-future-integrations)
30. [Technology Stack](#30-technology-stack)
31. [Success Criteria](#31-success-criteria)

---

# 1. Architecture Overview

## Style

| Principle | Choice | Reason |
|---|---|---|
| Structure | Modular Monolith | Simple deployment, easy debugging, lower ops cost |
| Design | Clean Architecture + DDD | Business logic independent of framework/infra |
| Communication | Event Driven (RabbitMQ) | Decoupled AI layer, zero DB access from workers |
| Query | CQRS (selective) | Heavy read paths separated from write paths |
| Future | Microservice-ready | Each module can be extracted independently |

## Core Principle

> AI Workers **never touch the database**. They only publish events. The backend owns all persistence.

---

# 2. High Level System Architecture

```
┌──────────────────────────────────────────────────────┐
│                  React Dashboard                     │
│     TypeScript · Material UI · AG Grid · Recharts    │
│     TanStack Query · Zustand · React Hook Form       │
└──────────────────────────┬───────────────────────────┘
                           │ HTTPS / WSS
                           ▼
┌──────────────────────────────────────────────────────┐
│                  Nginx Reverse Proxy                 │
└──────────────────────────┬───────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│              FastAPI Backend (Modular Monolith)      │
│                                                      │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  REST API   │  │WebSocket │  │  RabbitMQ      │  │
│  │  /api/v1/   │  │  /ws/    │  │  Consumer      │  │
│  └─────────────┘  └──────────┘  └────────────────┘  │
│                                                      │
│  JWT Auth · RBAC · Redis Cache · Rate Limiting       │
│  Alembic Migrations · Structured Logging             │
└──────────┬─────────────────┬────────────────────────-┘
           │                 │
           ▼                 ▼
    ┌─────────────┐   ┌─────────────┐
    │ PostgreSQL  │   │    Redis    │
    │  (primary)  │   │  (cache +   │
    │             │   │  pub/sub)   │
    └─────────────┘   └─────────────┘

           │ Publish / Subscribe
           ▼
┌──────────────────────────────────────────────────────┐
│                    RabbitMQ                          │
│          Events Queue + Dead Letter Queue            │
└──────────────────────────┬───────────────────────────┘
                           │ Publish Events
                           ▼
┌──────────────────────────────────────────────────────┐
│                 AI Worker Pool                       │
│   YOLO · ByteTrack · OpenCV · ONNX Runtime           │
│   Rules Engine · Config Sync · Health Monitor        │
└──────────────────────────┬───────────────────────────┘
                           │ RTSP
                           ▼
┌──────────────────────────────────────────────────────┐
│               Factory RTSP Cameras                   │
│          Auto-reconnect · Health Polling             │
└──────────────────────────────────────────────────────┘
```

---

# 3. Physical Architecture

## Frontend

Technology: React 18 · TypeScript · Vite · Material UI · AG Grid · Recharts · TanStack Query · Zustand · React Hook Form · Zod

Responsibilities:
- Executive, Safety, Camera, and Analytics dashboards
- Real-time alert feed (WebSocket)
- Zone configuration management
- Report generation (PDF / Excel download)
- User and role management (Admin only)

## Backend

Technology: FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · PostgreSQL · Redis

Responsibilities:
- JWT authentication + refresh token rotation
- Role-based access control (RBAC)
- REST API with versioning, pagination, filtering, sorting
- WebSocket hub for real-time dashboard and alert push
- RabbitMQ consumer — processes AI worker events
- Redis cache management
- Alert lifecycle management
- Notification dispatch
- Analytics aggregation
- PDF + Excel report generation
- Audit logging

## AI Worker

Technology: Python · YOLO · OpenCV · ByteTrack · ONNX Runtime · PyTorch · CUDA / CPU

Responsibilities:
- RTSP stream capture per camera
- Frame sampling (2 FPS from 25 FPS)
- Person + PPE detection (YOLO)
- Multi-object tracking (ByteTrack)
- Occupancy counting per zone
- Rules engine evaluation
- Violation snapshot capture
- RabbitMQ event publishing
- Zone config sync (hot-reload on change)
- Model hot-swap (no stream restart)
- Worker heartbeat + health metrics

---

# 4. Modular Monolith — Module Breakdown

```
backend/src/modules/

├── identity/         Users, roles, permissions, JWT, sessions
├── organization/     Multi-tenant support (future)
├── factory/          Factory CRUD, plant head assignment
├── zone/             Zone management, occupancy rules, supervisor
├── camera/           Camera registry, RTSP config, health status
├── worker/           AI worker registry, heartbeat, assignment
├── occupancy/        Real-time count logs, peak tracking
├── ppe/              Violation records, snapshot references
├── alerts/           Alert creation, lifecycle, history, assignment
├── notifications/    Email, in-app, web push, Slack, Teams, webhook
├── analytics/        Aggregated KPIs, trends, heatmaps, safety score
├── dashboard/        Dashboard summary APIs (cached)
├── reports/          PDF + Excel generation, download
├── config/           Zone-level detection config, version management
├── audit/            Immutable audit log, compliance export
└── health/           /health/ready + /health/live endpoints
```

### Module Isolation Rules

- No module imports from another module's `infrastructure/` layer
- Cross-module communication via:
  - Domain events (async, within process)
  - Application service interfaces (sync, within process)
  - RabbitMQ events (async, AI worker ↔ backend)

---

# 5. Clean Architecture — Per Module Structure

```
module/
├── api/
│   ├── routes.py             FastAPI router
│   ├── request_models.py     Pydantic input schemas
│   └── response_models.py    Pydantic output schemas
│
├── application/
│   ├── commands/             Write operations (CreateAlert, ResolveAlert)
│   ├── queries/              Read operations (GetAlertList, GetAlertDetail)
│   └── services/             Orchestration between domain + infra
│
├── domain/
│   ├── entities.py           Core business objects
│   ├── value_objects.py      Immutable domain concepts
│   ├── events.py             Domain events raised by entities
│   ├── repositories.py       Repository interfaces (abstract)
│   └── rules.py              Business rule validation
│
├── infrastructure/
│   ├── models.py             SQLAlchemy ORM models
│   ├── repositories.py       Concrete repository implementations
│   └── external/             Third-party clients (email, push, etc.)
│
└── tests/
    ├── unit/
    └── integration/
```

### Example: Alert Module Flow

```
POST /api/v1/alerts/{id}/resolve
    ↓
AlertRouter → ResolveAlertCommand
    ↓
ResolveAlertHandler
    ↓
AlertRepository.get(id)                  ← domain
Alert.resolve(user_id, comment)          ← domain rule
AlertRepository.save(alert)              ← infrastructure
AlertResolvedEvent published             ← domain event
    ↓
NotificationService.notify_supervisor()  ← cross-module via interface
AuditService.log(action)                 ← cross-module via interface
WebSocketManager.broadcast(alert)        ← real-time push
CacheService.invalidate("alert:*")       ← cache invalidation
```

---

# 6. Authentication & Authorization

## JWT Strategy

```
POST /api/v1/auth/login
    ↓
Credentials validated
    ↓
Access Token (JWT)     → expires in 8 hours
Refresh Token (opaque) → expires in 7 days
    ↓
Access Token  → returned in response body (stored in memory by client)
Refresh Token → returned in HttpOnly cookie (never accessible via JS)
```

## Refresh Token Rotation

```
Access Token expires
    ↓
Client sends Refresh Token (via HttpOnly cookie)
    ↓
Backend validates token hash against identity.refresh_tokens
    ↓
Old token revoked (status = Revoked)
New Access Token + new Refresh Token issued
    ↓
Replay attack: old token used → all tokens for user revoked → force re-login
```

## Token Blacklisting on Logout

```
POST /api/v1/auth/logout
    ↓
Refresh Token revoked in DB
Access Token JTI added to Redis blacklist
TTL = remaining token lifetime
    ↓
Every authenticated request checks Redis blacklist
Blacklisted token → 401 Unauthorized
```

## Role Based Access Control (RBAC)

Roles: `Admin` · `SafetyOfficer` · `Supervisor` · `Viewer`

Permissions stored as JSONB per role:

```json
{
  "alerts":    ["read", "acknowledge", "resolve"],
  "cameras":   ["read"],
  "config":    [],
  "users":     [],
  "audit":     [],
  "reports":   ["generate", "download"]
}
```

Permission check enforced in the API layer on every request.
Unauthorized access → `403 Forbidden` + audit log entry.

---

# 7. Event Driven Architecture

## Event Flow

```
Camera
    ↓
AI Detection
    ↓
Rules Engine Evaluation
    ↓
Event Created (with snapshot_key, confidence, zone_id, camera_id)
    ↓
RabbitMQ — main exchange
    ↓ (on failure → Dead Letter Queue)
Backend Consumer
    ↓
PostgreSQL (violation + alert created)
    ↓
Redis cache invalidated
    ↓
WebSocket broadcast to connected supervisors
    ↓
Notification dispatched (email + in-app + web push)
    ↓
Audit log entry created
```

## All Events

| Event | Publisher | Routing Key |
|---|---|---|
| OccupancyUpdated | AI Worker | `events.occupancy_updated` |
| HelmetMissingDetected | AI Worker | `events.helmet_missing_detected` |
| VestMissingDetected | AI Worker | `events.vest_missing_detected` |
| GlovesMissingDetected | AI Worker | `events.gloves_missing_detected` |
| ShoesMissingDetected | AI Worker | `events.shoes_missing_detected` |
| OvercrowdingDetected | AI Worker | `events.overcrowding_detected` |
| UnauthorizedEntryDetected | AI Worker | `events.unauthorized_entry_detected` |
| CameraOfflineDetected | AI Worker | `events.camera_offline_detected` |
| CameraReconnected | AI Worker | `events.camera_reconnected` |
| WorkerHeartbeat | AI Worker | `events.worker_heartbeat` |
| ModelUpdated | Backend | `config.model_updated` |
| ConfigUpdated | Backend | `config.zone_config_updated` |

## Event Payload Example

```json
{
  "event":        "helmet_missing_detected",
  "event_id":     "uuid-v4",
  "camera_id":    "CAM-001",
  "zone_id":      "ZONE-WELDING",
  "factory_id":   "FACTORY-GN",
  "timestamp":    "2026-01-01T10:00:00Z",
  "confidence":   0.91,
  "snapshot_key": "snapshots/ZONE-WELDING/CAM-001/2026-01-01T10-00-00.jpg",
  "worker_id":    "worker-1"
}
```

## Dead Letter Queue (DLQ)

```
Processing fails
    ↓
Attempt 1: immediate retry
Attempt 2: 30 seconds
Attempt 3: 5 minutes
Attempt 4: → DLQ (manual review)
    ↓
Background job monitors DLQ depth
DLQ depth > 100 → Prometheus alert → operations team notified
```

---

# 8. AI Worker Architecture

## Worker Design

Each worker process manages multiple cameras independently:

```
Worker Process
├── CameraWorker (CAM-001) — runs in thread/coroutine
├── CameraWorker (CAM-002)
├── CameraWorker (CAM-003)
└── ... up to 20–25 cameras per worker
```

## Detection Pipeline (per camera)

```
RTSP Stream
    ↓
FrameReader — capture + auto-reconnect
    ↓
Frame Sampling — 2 FPS from 25 FPS (configurable)
    ↓
YOLO Detector — person + PPE detection
    ↓
Confidence Threshold Check (zone-configurable)
    ↓
ByteTrack Tracker — assign track IDs
    ↓
OccupancyCounter — count persons in zone
    ↓
PPEValidator — check required PPE per tracked person
    ↓
RulesEngine — evaluate violation conditions
    ↓
SnapshotCapture — save frame to MinIO on violation
    ↓
RabbitMQPublisher — publish event
```

## Default Confidence Thresholds

| Detection | Default | Configurable |
|---|---|---|
| Person | 0.70 | Per zone |
| Helmet | 0.75 | Per zone |
| Safety Vest | 0.75 | Per zone |
| Gloves | 0.70 | Per zone |
| Safety Shoes | 0.70 | Per zone |

## RTSP Resilience

```
Stream lost
    ↓
Retry: 5 seconds
Retry: 15 seconds
Retry: 60 seconds
    ↓ (still offline)
Publish CameraOfflineDetected
Backend creates High severity alert
IT team notified
Worker continues all other cameras
```

## Circuit Breaker

```
3 consecutive processing failures on same camera
    ↓
Camera isolated from worker
CameraOfflineDetected published
Worker continues remaining cameras
```

## Worker ↔ Backend Config Sync (Race Condition Safe)

```
Worker starts
    ↓
Step 1: Pull full config from REST API → /api/v1/config/zone/{zone_id}
        (authoritative source, includes current version number)
    ↓
Step 2: Subscribe to RabbitMQ config.zone_config_updated
    ↓
ConfigUpdated event received
    ↓
Compare event.version vs local_version
    ↓
event.version > local_version  → apply + update local_version
event.version <= local_version → discard (stale, already have latest)
```

## Model Hot-Swap

```
Admin uploads new model via backend API
    ↓
New model stored in MinIO model registry
Backend publishes ModelUpdated event
    ↓
All workers receive event
Worker downloads new model weights
Worker swaps model (stream continues, no restart)
Worker publishes WorkerHeartbeat with new model version
```

## Worker Metrics (Prometheus)

```
worker_frames_processed_total         — total frames processed
worker_frames_dropped_total           — frames dropped (queue overflow)
worker_inference_latency_seconds      — per-frame inference time (histogram)
worker_detection_count_total          — detections by type
worker_queue_depth                    — RabbitMQ publish queue depth
worker_camera_reconnect_total         — camera reconnection attempts
worker_circuit_breaker_open_total     — cameras isolated by circuit breaker
worker_heartbeat_timestamp            — last heartbeat (liveness check)
worker_model_version                  — active model version
```

---

# 9. Rules Engine

Rules are **not hardcoded** — they are stored in the database and loaded per zone.

## Rule Structure

```python
Rule:
  id:              UUID
  zone_id:         UUID
  condition_type:  Enum (HELMET_MISSING, VEST_MISSING, OVERCROWDING, ...)
  duration_seconds: int   # sustained for N seconds before alert
  severity:        Enum (CRITICAL, HIGH, MEDIUM, LOW)
  enabled:         bool
  actions:         List[Enum] (CREATE_ALERT, SEND_NOTIFICATION, STORE_SNAPSHOT, LOG_AUDIT)
```

## Example Rules

```
Rule 1:
  IF person_detected AND helmet_missing
  FOR 3 seconds
  THEN create_alert(severity=HIGH) + store_snapshot + notify_supervisor

Rule 2:
  IF current_count > zone.max_occupancy
  FOR 0 seconds (immediate)
  THEN create_alert(severity=HIGH) + notify_supervisor

Rule 3:
  IF camera_offline
  FOR 60 seconds
  THEN create_alert(severity=HIGH) + notify_it_team

Rule 4:
  IF person_detected IN restricted_zone
  FOR 0 seconds
  THEN create_alert(severity=HIGH) + store_snapshot + notify_security
```

## Rules Engine Evaluation

```python
for tracked_person in current_frame_persons:
    for rule in zone.active_rules:
        if rule.condition_type == HELMET_MISSING:
            if not tracked_person.has_helmet:
                violation_tracker.record(tracked_person.track_id, rule)
                if violation_tracker.duration(tracked_person.track_id) >= rule.duration_seconds:
                    execute_actions(rule.actions, tracked_person, frame)
```

Duration tracking persists across frames using track IDs from ByteTrack.

---

# 10. WebSocket & Real-Time Architecture

## Why WebSocket

200 concurrent supervisors polling every 2 seconds = 6,000 requests/minute on backend + DB. WebSocket push eliminates this entirely — the backend pushes only when data changes.

## Connection Manager

```python
class WebSocketConnectionManager:
    connections: Dict[str, List[WebSocket]]   # user_id → sockets
    role_index:  Dict[str, Set[str]]          # role → user_ids

    async def connect(user_id, role, websocket)
    async def disconnect(user_id, websocket)
    async def send_to_user(user_id, message)
    async def broadcast_to_role(role, message)
    async def broadcast_to_all(message)
```

## Channels

| Channel | Message Types |
|---|---|
| `/ws/dashboard` | OccupancyUpdated, CameraStatusChanged, SafetyScoreUpdated |
| `/ws/alerts` | AlertCreated, AlertAcknowledged, AlertResolved, AlertAssigned |

## Redis Pub/Sub for Multi-Instance Scaling

```
Backend Instance A receives AlertCreated from RabbitMQ
    ↓
Instance A handles DB write + cache invalidation
    ↓
Instance A publishes to Redis channel: ws:alerts:supervisor
    ↓
All backend instances subscribe to ws:* Redis channels
    ↓
Each instance broadcasts to its locally connected WebSocket clients
    ↓
All supervisors receive the alert regardless of which instance they hit
```

## Concurrent Connection Limits

| Role | Max WebSocket Connections |
|---|---|
| Viewer | 3 |
| Supervisor | 5 |
| Safety Officer | 5 |
| Admin | 10 |

Exceeded limit → `4008 Too Many Connections` close code.

---

# 11. API Design & Versioning

## URL Structure

```
/api/v1/resource
/api/v2/resource    ← future breaking changes
```

## Standard Response Model

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 145,
    "total_pages": 8
  },
  "error": null
}
```

## Error Response

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ALERT_NOT_FOUND",
    "message": "Alert with id abc-123 does not exist",
    "details": {}
  }
}
```

## Query Parameters (all list endpoints)

```
?page=1&page_size=20
?sort_by=created_on&sort_dir=desc
?filter[status]=Open
?search=welding
```

## Versioning Policy

| Change Type | Version Bump |
|---|---|
| Add optional field to response | No |
| Add new endpoint | No |
| Remove or rename field | Yes (v2) |
| Change field type | Yes (v2) |
| Remove endpoint | Yes (v2) |

Deprecated v1 endpoints return:
```
Deprecation: true
Sunset: 2027-06-01
X-API-Version: v1
```

v1 maintained for minimum 6 months after v2 release.

---

# 12. Caching Strategy

Redis is the primary cache layer. Cache is event-driven — invalidated on every write, not on TTL alone.

## What is Cached

| Key Pattern | Content | TTL |
|---|---|---|
| `dashboard:summary:{factory_id}` | Executive dashboard stats | 30s |
| `zone:occupancy:{zone_id}` | Current occupancy count | 10s |
| `camera:status:all` | Camera online/offline list | 15s |
| `alert:count:{zone_id}` | Open alert count per zone | 30s |
| `snapshot:url:{snapshot_key}` | MinIO pre-signed URL | 14 min |
| `user:permissions:{user_id}` | RBAC permission set | 1 hour |
| `zone:config:{zone_id}` | Detection config per zone | until invalidated |

## Cache Invalidation

```
Backend consumer receives OccupancyUpdated event
    ↓
occupancy.logs row inserted
    ↓
Redis.delete("zone:occupancy:{zone_id}")
Redis.delete("dashboard:summary:{factory_id}")
    ↓
Next dashboard request fetches fresh data and repopulates cache
```

---

# 13. Database Architecture

Database: PostgreSQL 16 with native table partitioning.

## Schema Overview

```
identity          → users, roles, permissions, refresh_tokens
organization      → organizations (future multi-tenant)
factory           → factories
zone              → zones
camera            → cameras
worker            → ai_workers
occupancy         → logs (partitioned by month)
ppe               → violations (partitioned by month)
alerts            → alerts, alert_history
notifications     → notification_log
config            → zone_configs
audit             → audit_log
analytics         → pre-aggregated analytics (materialized views)
```

## Core Tables

### identity.users
```
id                UUID PK
name              VARCHAR
email             VARCHAR UNIQUE
password_hash     VARCHAR
role_id           FK → identity.roles
status            ENUM (Active, Inactive, Suspended)
created_on        TIMESTAMPTZ
last_login_at     TIMESTAMPTZ
created_by        FK → identity.users
modified_by       FK → identity.users
version           INT DEFAULT 1
deleted_at        TIMESTAMPTZ (soft delete)
```

### identity.roles
```
id                UUID PK
name              VARCHAR UNIQUE (Admin, SafetyOfficer, Supervisor, Viewer)
permissions       JSONB
created_on        TIMESTAMPTZ
```

### identity.refresh_tokens
```
id                UUID PK
user_id           FK → identity.users
token_hash        VARCHAR (SHA-256, never plaintext)
expires_at        TIMESTAMPTZ
status            ENUM (Active, Revoked)
created_at        TIMESTAMPTZ
revoked_at        TIMESTAMPTZ
```

### factory.factories
```
id                UUID PK
name              VARCHAR
code              VARCHAR UNIQUE
address           TEXT
location          VARCHAR
plant_head_id     FK → identity.users
status            ENUM (Active, Inactive)
created_on        TIMESTAMPTZ
created_by        FK → identity.users
modified_by       FK → identity.users
version           INT DEFAULT 1
deleted_at        TIMESTAMPTZ
```

### zone.zones
```
id                UUID PK
factory_id        FK → factory.factories
name              VARCHAR
code              VARCHAR UNIQUE
max_occupancy     INT
supervisor_id     FK → identity.users
description       TEXT
status            ENUM (Active, Inactive)
created_on        TIMESTAMPTZ
created_by        FK → identity.users
modified_by       FK → identity.users
version           INT DEFAULT 1
deleted_at        TIMESTAMPTZ
```

### camera.cameras
```
id                UUID PK
zone_id           FK → zone.zones
name              VARCHAR
code              VARCHAR UNIQUE
rtsp_url          VARCHAR (encrypted at rest)
status            ENUM (Online, Offline, Degraded)
fps               DECIMAL
last_seen_at      TIMESTAMPTZ
worker_id         FK → worker.ai_workers
created_on        TIMESTAMPTZ
created_by        FK → identity.users
modified_by       FK → identity.users
version           INT DEFAULT 1
deleted_at        TIMESTAMPTZ
```

### config.zone_configs
```
id                UUID PK
zone_id           FK → zone.zones UNIQUE
person_threshold  DECIMAL DEFAULT 0.70
helmet_threshold  DECIMAL DEFAULT 0.75
vest_threshold    DECIMAL DEFAULT 0.75
gloves_threshold  DECIMAL DEFAULT 0.70
shoes_threshold   DECIMAL DEFAULT 0.70
max_occupancy     INT
ppe_required      JSONB   (["helmet", "vest", "gloves"])
updated_by        FK → identity.users
updated_at        TIMESTAMPTZ
version           INT DEFAULT 1   ← incremented on every save
```

Workers use `version` to safely discard stale config events during restarts.

### occupancy.logs (partitioned by month)
```
id                UUID PK
zone_id           FK → zone.zones
camera_id         FK → camera.cameras
current_count     INT
timestamp         TIMESTAMPTZ
```

Partition by: `PARTITION BY RANGE (timestamp)`
Retain 12 months online. Archive older to cold storage.

### ppe.violations (partitioned by month)
```
id                UUID PK
zone_id           FK → zone.zones
camera_id         FK → camera.cameras
violation_type    ENUM (HELMET_MISSING, VEST_MISSING, GLOVES_MISSING, SHOES_MISSING, OVERCROWDING, UNAUTHORIZED_ENTRY)
confidence        DECIMAL
snapshot_key      VARCHAR   (MinIO object key, not a local path)
track_id          VARCHAR   (ByteTrack track ID)
created_on        TIMESTAMPTZ
```

### alerts.alerts
```
id                UUID PK
violation_id      FK → ppe.violations (nullable for camera alerts)
factory_id        FK → factory.factories
zone_id           FK → zone.zones
camera_id         FK → camera.cameras
alert_type        ENUM
severity          ENUM (Critical, High, Medium, Low)
status            ENUM (Open, Acknowledged, InProgress, Closed)
assigned_to       FK → identity.users
created_on        TIMESTAMPTZ
acknowledged_on   TIMESTAMPTZ
resolved_on       TIMESTAMPTZ
created_by        VARCHAR (system or user_id)
```

### alerts.alert_history
```
id                UUID PK
alert_id          FK → alerts.alerts
from_status       ENUM
to_status         ENUM
changed_by        FK → identity.users
changed_at        TIMESTAMPTZ
comment           TEXT
```

### notifications.notification_log
```
id                UUID PK
alert_id          FK → alerts.alerts
channel           ENUM (Email, InApp, WebPush, Slack, Teams, Webhook)
recipient_id      FK → identity.users
sent_at           TIMESTAMPTZ
status            ENUM (Sent, Failed, Delivered)
failure_reason    TEXT
retry_count       INT DEFAULT 0
```

### audit.audit_log (immutable — no UPDATE/DELETE permitted)
```
id                UUID PK
user_id           FK → identity.users
action            VARCHAR (AlertResolved, ConfigChanged, UserCreated, ...)
entity_type       VARCHAR
entity_id         UUID
old_value         JSONB
new_value         JSONB
ip_address        VARCHAR
user_agent        VARCHAR
correlation_id    VARCHAR
timestamp         TIMESTAMPTZ
```

## Indexes

```sql
-- Alerts
CREATE INDEX idx_alerts_status ON alerts.alerts(status);
CREATE INDEX idx_alerts_zone_id ON alerts.alerts(zone_id);
CREATE INDEX idx_alerts_created_on ON alerts.alerts(created_on DESC);
CREATE INDEX idx_alerts_severity ON alerts.alerts(severity);

-- Occupancy (partition-aware)
CREATE INDEX idx_occupancy_zone_ts ON occupancy.logs(zone_id, timestamp DESC);

-- Violations (partition-aware)
CREATE INDEX idx_violations_zone ON ppe.violations(zone_id, created_on DESC);
CREATE INDEX idx_violations_type ON ppe.violations(violation_type, created_on DESC);

-- Audit
CREATE INDEX idx_audit_user ON audit.audit_log(user_id, timestamp DESC);
CREATE INDEX idx_audit_entity ON audit.audit_log(entity_type, entity_id);
```

---

# 14. Snapshot Storage Architecture

Violation snapshots → MinIO (on-prem) or AWS S3 (cloud).

## Key Format

```
snapshots/{factory_id}/{zone_id}/{camera_id}/{YYYY-MM-DD}/{HH-MM-SS}.jpg
```

## Pre-Signed URL Strategy

```
Frontend requests alert detail (includes snapshot_key)
    ↓
Backend checks Redis: snapshot:url:{snapshot_key}
    ↓ (cache miss)
Backend calls MinIO.presigned_get_url(key, expiry=15min)
    ↓
URL stored in Redis with TTL = 14 minutes (1 min safety buffer)
    ↓
URL returned to frontend
    ↓ (cache hit)
Cached URL returned — no MinIO API call
```

Snapshots are never served from local disk. No direct MinIO URLs exposed to clients.

## URL Refresh Endpoint

If a URL expires while the user has the page open:

```
GET /api/v1/snapshots/{snapshot_key}/url
→ Returns a fresh 15-minute pre-signed URL
```

---

# 15. Data Retention Policy

| Table | Online | Cold Archive | Purge |
|---|---|---|---|
| occupancy.logs | 12 months | 2 years | After 2 years |
| ppe.violations | 24 months | 3 years | After 3 years |
| alerts.alerts | 24 months | 3 years | After 3 years |
| audit.audit_log | 36 months | 5 years | After 5 years |
| snapshots (MinIO) | 90 days | 1 year | After 1 year |
| identity.refresh_tokens | 7 days | — | Auto-purged |

Automated: a nightly background job runs partition archival and MinIO lifecycle policy enforces snapshot retention.

---

# 16. Dashboard Architecture

## Executive Dashboard (Admin / Plant Manager)

| Metric | Source |
|---|---|
| Total Cameras | cache: camera:status:all |
| Online / Offline Cameras | cache: camera:status:all |
| Active Alerts | cache: alert:count:* |
| PPE Compliance % | analytics materialized view |
| Safety Score | computed from compliance + incident rate |
| Today's Violations | analytics |

## Safety Dashboard (Safety Officer)

- Violations by type (today / this week / this month)
- Open alerts with severity breakdown
- Alert resolution time trend
- Violation heatmap by zone

## Zone Dashboard (Supervisor)

- Current occupancy vs limit (real-time via WebSocket)
- Current violations in assigned zones
- Camera status for assigned zone
- Recent alerts for zone

## Camera Dashboard

- Camera grid with live status
- FPS per camera
- Last seen timestamp
- Worker assignment
- Stream health indicator

---

# 17. Analytics Architecture

## KPIs

| KPI | Calculation |
|---|---|
| Helmet Compliance % | (frames with helmet / total person frames) × 100 |
| Vest Compliance % | (frames with vest / total person frames) × 100 |
| PPE Compliance % | average of all PPE compliance metrics |
| Safety Score | 0.6 × PPE Compliance + 0.3 × (1 - incident rate) + 0.1 × alert closure speed |
| Alert Response Time | avg(acknowledged_on - created_on) |
| Alert Closure Time | avg(resolved_on - created_on) |
| Peak Occupancy | max(current_count) per zone per day |
| Overcrowding Frequency | count(overcrowding events) per zone per week |

## Trend Periods

- Daily (last 30 days)
- Weekly (last 12 weeks)
- Monthly (last 12 months)

## Violation Heatmap

Zone × Hour grid showing violation density. Used to identify high-risk time windows.

## Report Export

- PDF: generated server-side using WeasyPrint / ReportLab
- Excel: generated using openpyxl

---

# 18. Notification Architecture

## Channels

| Channel | Library | Use Case |
|---|---|---|
| Email | SMTP (SendGrid / self-hosted) | Alert + daily summary |
| In-App | WebSocket push | Real-time alerts |
| Web Push | Web Push API | Browser notifications |
| Slack | Slack Webhook API | Team channel alerts |
| Microsoft Teams | Teams Webhook API | Enterprise teams |
| Webhook | HTTP POST | Custom integrations |

## Notification Templates

Templates are stored in DB — configurable per organization per event type.

```
Template: helmet_missing_alert
Subject:  "[HIGH] Helmet Violation — {zone_name} — {timestamp}"
Body:     "A helmet violation was detected at {zone_name} by {camera_name}.
           View alert: {alert_url}"
```

## Delivery Flow

```
Violation detected
    ↓
Alert created
    ↓
NotificationService.dispatch(alert)
    ↓
For each recipient in alert.zone.supervisors:
    For each channel in user.notification_preferences:
        ChannelAdapter.send(template, recipient, alert)
        notification_log.insert(status=Sent/Failed)
    ↓
Failed delivery:
    Retry 1: +30s
    Retry 2: +2min
    Retry 3: +10min
    All failed → operations team notified
```

---

# 19. Zone Configuration Flow

## Runtime Config Change (No Restart)

```
Admin updates zone config via PUT /api/v1/config/zone/{zone_id}
    ↓
config.zone_configs updated (version += 1)
Audit log entry created
    ↓
ConfigUpdated event published to RabbitMQ
Event payload includes: zone_id, new_config, new_version
    ↓
All AI workers subscribed to config.zone_config_updated receive event
    ↓
Each worker: compare event.version vs local_config.version
    ↓
event.version > local → apply new config, update local_version
event.version ≤ local → discard (stale)
    ↓
Detection thresholds + PPE rules updated live
No camera stream restart required
```

---

# 20. API Rate Limiting

Limits enforced per user per role using Redis sliding window counter.

| Role | Limit |
|---|---|
| Viewer | 60 req/min |
| Supervisor | 120 req/min |
| Safety Officer | 120 req/min |
| Admin | 300 req/min |

Rate limit exceeded → `429 Too Many Requests` + `Retry-After` header.

Response headers on every request:
```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1735700460
```

WebSocket connections are not subject to HTTP rate limits (governed by connection limits per role).

---

# 21. Security Architecture

## OWASP Top 10 Coverage

| Risk | Mitigation |
|---|---|
| Injection | SQLAlchemy ORM parameterized queries; no raw SQL |
| Broken Auth | JWT + refresh rotation + blacklisting; HttpOnly cookies |
| XSS | React escapes by default; CSP headers via Nginx |
| CSRF | SameSite=Strict on cookies; token in header for API calls |
| Security Misconfiguration | Helmet headers via Nginx; strict CORS allowlist |
| Sensitive Data Exposure | RTSP URLs encrypted at rest; snapshots behind pre-signed URLs |
| Broken Access Control | RBAC on every endpoint; permission check in middleware |
| Logging & Monitoring | Structured JSON logs; Prometheus + Grafana + Loki |
| SSRF | RTSP URL validation against allowlist before saving |
| Insecure Deserialization | Pydantic v2 strict parsing on all inputs |

## Additional

- Input validation: Pydantic v2 on all request bodies
- File upload: JPEG/PNG only, max 5MB, scanned for mime-type mismatch
- Secrets: environment variables only; never committed to repo
- HTTPS enforced in production via Nginx
- All WebSocket connections over WSS

---

# 22. Monitoring & Observability

## Prometheus — Backend Metrics

```
http_requests_total                  — by endpoint, method, status_code
http_request_duration_seconds        — latency histogram
active_websocket_connections         — current live connections
rabbitmq_events_consumed_total       — by event type
rabbitmq_events_failed_total         — events sent to DLQ
dlq_depth                            — current DLQ message count
alert_created_total                  — by severity
alert_resolution_seconds             — time open → resolved (histogram)
cache_hit_total                      — by key prefix
cache_miss_total                     — by key prefix
```

## Prometheus — AI Worker Metrics

```
worker_frames_processed_total
worker_frames_dropped_total
worker_inference_latency_seconds     — p50, p90, p99
worker_detection_count_total         — by detection_type
worker_queue_depth
worker_camera_reconnect_total
worker_circuit_breaker_open_total
worker_heartbeat_timestamp
worker_model_version
```

## Grafana Dashboards

| Dashboard | Key Panels |
|---|---|
| System Overview | RPS, error rate, p99 latency, active connections |
| AI Worker Health | Inference latency histogram, frames/sec, queue depth per worker |
| Alert Operations | Alert volume by hour, resolution time trend, open by severity |
| Camera Health | Online/offline ratio, reconnection rate, circuit breaker count |
| DLQ Monitor | DLQ depth over time, failed events by type |

## Alertmanager Rules

| Condition | Severity | Destination |
|---|---|---|
| DLQ depth > 100 | Critical | PagerDuty |
| Worker heartbeat missing > 60s | Critical | PagerDuty |
| API error rate > 5% | High | PagerDuty |
| Inference latency p99 > 2s | Medium | Slack |
| Camera offline > 60s | Medium | In-app alert to supervisor |

---

# 23. Audit Trail

Every sensitive action written to `audit.audit_log`:

| Action | Trigger |
|---|---|
| AlertAcknowledged | Supervisor acknowledges alert |
| AlertResolved | Supervisor resolves alert |
| AlertReassigned | Alert assigned to different user |
| ConfigChanged | Zone config updated |
| UserCreated | New user added |
| UserDisabled | User account disabled |
| RoleChanged | User role changed |
| CameraAdded | Camera registered |
| CameraRemoved | Camera deleted |
| ModelUpdated | AI model version changed |
| LoginFailed | Failed authentication attempt |
| UnauthorizedAccess | 403 response on any endpoint |
| Logout | Session terminated |

Rules:
- Audit log is **append-only** — no UPDATE or DELETE permitted at DB level (row-level security)
- Accessible only to Admin role
- Exported as PDF for compliance audits

---

# 24. Logging Strategy

## Format

All services emit structured JSON logs:

```json
{
  "timestamp":      "2026-01-01T10:00:00.123Z",
  "level":          "INFO",
  "service":        "visionguard-backend",
  "module":         "alerts",
  "correlation_id": "req-abc-123",
  "user_id":        "user-xyz",
  "message":        "Alert resolved",
  "alert_id":       "alert-456",
  "duration_ms":    45
}
```

## Log Levels

| Level | When |
|---|---|
| ERROR | Unhandled exceptions, DLQ overflow, auth failures |
| WARNING | High DLQ depth, slow inference, degraded camera |
| INFO | Normal operations — alert created, config changed |
| DEBUG | Disabled in production |

## Correlation IDs

Every HTTP request gets a `X-Correlation-ID` header (generated if not provided).
Propagated to all log entries and downstream service calls within that request scope.

---

# 25. Testing Strategy

## Backend

```
Unit Tests       → domain entities, business rules, use case handlers
Integration Tests → repository implementations (real PostgreSQL)
API Tests         → FastAPI TestClient, full request/response cycle
Coverage target  → ≥ 80%
```

## AI Worker

```
Unit Tests        → rules engine logic, frame sampling, config sync
Pipeline Tests    → mock camera feed → mock detection → event assertion
Coverage target   → ≥ 70%
```

## Frontend

```
Unit Tests        → Zustand store, utility functions
Component Tests   → React Testing Library
Coverage target   → ≥ 70%
```

---

# 26. CI/CD Pipeline

GitHub Actions — runs on every push to `main` and all pull requests.

```yaml
Pipeline:
  lint:
    - ruff (Python)
    - eslint (TypeScript)

  format:
    - black (Python)
    - prettier (TypeScript)

  test:
    - pytest (backend + AI worker)
    - vitest (frontend)

  build:
    - docker build backend
    - docker build ai-worker
    - docker build frontend

  push: (main branch only)
    - push images to container registry

  deploy: (main branch only, manual trigger for prod)
    - docker compose pull
    - docker compose up --no-deps -d
```

---

# 27. Deployment Architecture

## Development

```
Single machine (laptop / workstation)

React (Vite dev server)
FastAPI (uvicorn --reload)
PostgreSQL (Docker)
RabbitMQ (Docker)
Redis (Docker)
MinIO (Docker)
AI Worker (CPU mode)
```

## Production — 50 Cameras (Initial Target)

```
Server 1 (Application)
├── Nginx (reverse proxy + SSL termination)
├── React (built static files served by Nginx)
├── FastAPI (gunicorn + uvicorn workers)
├── PostgreSQL
├── RabbitMQ
├── Redis
├── MinIO
├── Prometheus + Grafana + Loki

Server 2 (GPU Worker)
└── AI Worker 1 (25 cameras)

Server 3 (GPU Worker)
└── AI Worker 2 (25 cameras)
```

## Production — 200 Cameras

```
Server 1          → Nginx + React
Servers 2–3       → FastAPI (load balanced)
Server 4          → PostgreSQL (primary) + Redis + RabbitMQ + MinIO
Servers 5–12      → AI Workers (8 × 25 cameras)
Server 13         → Monitoring (Prometheus + Grafana + Loki)
```

Redis Pub/Sub used for WebSocket cross-instance broadcast.

---

# 28. Scaling Strategy

| Cameras | Backend | AI Workers | Notes |
|---|---|---|---|
| 50 | 1 server | 2 GPU workers | Initial target |
| 100 | 1 server | 4 GPU workers | |
| 200 | 2 servers (LB) | 8 GPU workers | Redis pub/sub for WS |
| 500 | 3–5 node cluster | 20+ workers | PG read replicas |
| 1000+ | API Gateway + cluster | 50+ workers | Kubernetes |

No code changes required at any scale — horizontal scaling only.

### PostgreSQL Scaling Path

```
100 cameras  → single primary
200 cameras  → primary + 1 read replica (analytics queries)
500 cameras  → primary + 2 read replicas + PgBouncer connection pool
1000 cameras → primary + 3 replicas + PgBouncer + Citus (if needed)
```

---

# 29. Future Integrations

| System | Purpose | Phase |
|---|---|---|
| SAP | Work order creation on violation | Phase 3 |
| HRMS | Worker identity, attendance | Phase 2 |
| Attendance System | Auto-link detected persons to employees | Phase 2 |
| Access Control System | Cross-reference badge entry vs camera entry | Phase 3 |
| Fire Alarm System | Correlate fire alarm with camera feed | Phase 3 |
| SMS Gateway | SMS alerts to supervisors | Phase 2 |
| Email Server | SMTP for email notifications | Phase 1 |

---

# 30. Technology Stack

| Category | Technology | License |
|---|---|---|
| Frontend | React 18 | MIT |
| | TypeScript | Apache 2.0 |
| | Vite | MIT |
| | Material UI | MIT |
| | AG Grid Community | MIT |
| | Recharts | MIT |
| | TanStack Query | MIT |
| | Zustand | MIT |
| | React Hook Form | MIT |
| | Zod | MIT |
| Backend | FastAPI | MIT |
| | SQLAlchemy 2.0 | MIT |
| | Alembic | MIT |
| | Pydantic v2 | MIT |
| AI | YOLO (Ultralytics) | AGPL v3 |
| | OpenCV | Apache 2.0 |
| | ByteTrack | MIT |
| | ONNX Runtime | MIT |
| | PyTorch | BSD |
| Database | PostgreSQL 16 | PostgreSQL License |
| Messaging | RabbitMQ | Mozilla PL 2.0 |
| Cache | Redis | BSD 3-Clause |
| Storage | MinIO | AGPL v3 |
| Monitoring | Prometheus | Apache 2.0 |
| | Grafana | AGPL v3 |
| | Loki | AGPL v3 |
| Infrastructure | Docker | Apache 2.0 |
| | Nginx | BSD 2-Clause |
| CI/CD | GitHub Actions | Free (public repos) |

All open source. Zero licensing cost for self-hosted deployment.

> Note: YOLO (Ultralytics) uses AGPL v3. For commercial closed-source deployments, an Ultralytics Enterprise license is required. Portfolio and internal enterprise use is covered under AGPL v3.

---

# 31. Success Criteria

| Criterion | Target |
|---|---|
| Helmet Detection Accuracy | ≥ 90% |
| Occupancy Accuracy | ≥ 95% |
| Alert Latency | ≤ 5 seconds |
| Camera Uptime Monitoring | offline detected within 60s |
| Camera Support (initial) | 50 cameras |
| Camera Support (future) | 200+ cameras |
| System Availability | 99.5% |
| Real-Time Dashboard | WebSocket-driven, zero polling |
| Historical Analytics | 24 months online |
| API Test Coverage | ≥ 80% |
| Worker Config Race Condition | safely handled via version comparison |
| Token Security | blacklisting on logout, refresh rotation |
| WebSocket Scaling | Redis pub/sub for multi-instance |
| Zero Data Loss | DLQ with 3-attempt retry |
| Audit Compliance | immutable audit log, all sensitive actions |

---

*End of Document*
