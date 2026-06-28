# IMPLEMENTATION.md

# VisionGuard AI

## Enterprise Factory Safety Monitoring Platform

---

# Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [High Level Architecture](#high-level-architecture)
3. [Physical Architecture](#physical-architecture)
4. [Modular Monolith Structure](#modular-monolith-structure)
5. [Clean Architecture Structure](#clean-architecture-structure)
6. [Event Driven Architecture](#event-driven-architecture)
7. [AI Architecture](#ai-architecture)
8. [Authentication & Authorization Architecture](#authentication--authorization-architecture)
9. [WebSocket & Real-Time Architecture](#websocket--real-time-architecture)
10. [API Design & Versioning](#api-design--versioning)
11. [Caching Strategy](#caching-strategy)
12. [Database Architecture](#database-architecture)
13. [Snapshot Storage Architecture](#snapshot-storage-architecture)
14. [Data Retention Policy](#data-retention-policy)
15. [Dashboard Architecture](#dashboard-architecture)
16. [API Rate Limiting](#api-rate-limiting)
17. [Security Architecture](#security-architecture)
18. [Notification Architecture](#notification-architecture)
19. [Zone Configuration Flow](#zone-configuration-flow)
20. [Monitoring & Observability](#monitoring--observability)
21. [Audit Trail](#audit-trail)
22. [Deployment Architecture](#deployment-architecture)
23. [Scaling Strategy](#scaling-strategy)
24. [Technology Stack](#technology-stack)
25. [Success Criteria](#success-criteria)

---

# Architecture Overview

## Architecture Style

The platform follows:

* Modular Monolith
* Clean Architecture
* Domain Driven Design (DDD)
* Event Driven Communication
* CQRS (Selective)
* Vertical Slice Principles

This architecture is chosen because:

* Easy development and deployment
* Lower operational cost
* Easier debugging
* Scales to 100–200 cameras initially
* AI workers can scale independently
* Future migration path to microservices

---

# High Level Architecture

```text
┌────────────────────────────────────┐
│          React Dashboard           │
│                                    │
│ Dashboard                          │
│ Camera Monitoring                  │
│ Occupancy Monitoring               │
│ Alerts                             │
│ Analytics                          │
└────────────────┬───────────────────┘
                 │ HTTP / WebSocket
                 ▼
┌────────────────────────────────────┐
│          FastAPI Backend           │
│      Modular Monolith Core         │
│      API Rate Limiting             │
│      JWT Auth + RBAC               │
│      Redis Cache                   │
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│             RabbitMQ               │
│    Event Communication + DLQ       │
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│           AI Worker Pool           │
│ OpenCV + RT-DETR + ByteTrack       │
│ Model Versioning + Thresholds      │
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│           RTSP Cameras             │
│   Reconnect / Health Polling       │
└────────────────────────────────────┘
```

---

# Physical Architecture

## Application Layer

### Frontend

Technology:

* React
* TypeScript
* Vite
* Material UI
* AG Grid

Responsibilities:

* Monitoring Dashboard
* Alert Dashboard
* Camera Dashboard
* Analytics
* Reporting

---

### Backend

Technology:

* FastAPI
* SQLAlchemy
* Alembic
* PostgreSQL
* Redis

Responsibilities:

* Authentication (JWT + Refresh Tokens)
* Authorization (RBAC)
* Business Rules
* Alert Processing
* Analytics
* Reporting
* Dashboard APIs
* WebSocket / SSE for real-time push
* API Rate Limiting (per user / per role)
* Caching (Redis)

---

### AI Layer

Technology:

* OpenCV
* RT-DETR
* ByteTrack
* PyTorch

Responsibilities:

* Person Detection
* Helmet Detection
* Vest Detection
* Occupancy Counting
* Tracking
* Model Version Management
* Confidence Threshold Evaluation

---

# Modular Monolith Structure

```text
backend/

src/

modules/

identity/
factory/
zone/
camera/
occupancy/
ppe/
alerts/
notifications/
analytics/
reports/
config/          ← zone-level config pushed to workers
audit/           ← compliance audit trail

shared/
database/
cache/           ← Redis client + helpers
realtime/        ← WebSocket connection manager
```

---

# Clean Architecture Structure

Every module follows:

```text
module/

api/
application/
domain/
infrastructure/
contracts/
```

---

## API Layer

Responsibilities:

* REST Endpoints
* WebSocket Endpoints
* Validation
* Authentication
* Request Processing
* Rate Limiting (per endpoint, per role)

Example:

```text
/api/v1/factories
/api/v1/zones
/api/v1/cameras
/api/v1/alerts
/api/v1/reports
/api/v1/config/zone/{zone_id}
/api/v1/audit
/ws/dashboard        ← WebSocket
/ws/alerts           ← WebSocket
```

---

## Application Layer

Responsibilities:

* Use Cases
* Command Handlers
* Query Handlers

Examples:

```text
CreateZoneHandler
CreateAlertHandler
GenerateReportHandler
CalculateOccupancyHandler
ResolveAlertHandler
PushZoneConfigHandler
LogAuditEventHandler
BroadcastAlertHandler      ← pushes to WebSocket clients
InvalidateDashboardCacheHandler
```

---

## Domain Layer

Contains:

* Entities
* Value Objects
* Domain Events
* Business Rules

Examples:

```text
Factory
Zone
OccupancyRule
Violation
Alert
ZoneConfig
AuditEntry
```

---

## Infrastructure Layer

Contains:

* PostgreSQL (via SQLAlchemy)
* RabbitMQ (with Dead Letter Queue)
* Redis (cache + pub/sub)
* Object Storage (S3-compatible MinIO)
* WebSocket Connection Manager
* External Services (email, push notifications)

---

# Event Driven Architecture

AI workers NEVER access database.

AI workers ONLY publish events.

Backend consumes events.

Failed events go to Dead Letter Queue (DLQ) for retry or manual inspection.

---

## Event Flow

```text
Camera

↓

AI Detection

↓

Event Creation

↓

RabbitMQ (main queue)

↓  (on failure)  →  Dead Letter Queue (DLQ)

Backend Consumer

↓

Database

↓

Redis Cache Invalidation

↓

WebSocket Broadcast

↓

Dashboard
```

---

## Events

```text
OccupancyUpdated
HelmetMissingDetected
VestMissingDetected
OvercrowdingDetected
CameraOfflineDetected
CameraReconnected
AlertCreated
AlertResolved
WorkerHeartbeat
ModelUpdated           ← triggers hot-swap in workers
ConfigUpdated          ← triggers config reload in workers
```

Example:

```json
{
  "event": "helmet_missing",
  "camera_id": "CAM-001",
  "zone_id": "ZONE-01",
  "timestamp": "2026-01-01T10:00:00",
  "confidence": 0.91,
  "snapshot_key": "snapshots/ZONE-01/CAM-001/2026-01-01T10:00:00.jpg"
}
```

---

## Dead Letter Queue (DLQ)

Failed events that cannot be processed are routed to a DLQ.

Retry policy:

```text
Attempt 1 → immediate
Attempt 2 → 30 seconds
Attempt 3 → 5 minutes
Attempt 4 → DLQ (manual review)
```

A background job checks the DLQ periodically and alerts the operations team.

---

# AI Architecture

## Worker Design

Each worker handles multiple cameras.

Example:

```text
Worker-1 → 20 Cameras
Worker-2 → 20 Cameras
Worker-3 → 20 Cameras
Worker-4 → 20 Cameras
```

Workers receive zone-level configuration from the backend at startup and on config-change events. No hardcoded thresholds.

---

## Detection Pipeline

```text
RTSP Stream

↓

Frame Capture (with reconnect on failure)

↓

Frame Sampling

↓

RT-DETR Detection

↓

Confidence Threshold Check

↓

ByteTrack Tracking

↓

Occupancy Calculation

↓

PPE Validation

↓

Snapshot Capture (on violation)

↓

Event Creation

↓

RabbitMQ
```

---

## Frame Sampling

To reduce GPU load:

```text
25 FPS Camera

↓

Process 2 FPS

↓

Detection

↓

Tracking
```

---

## Confidence Thresholds

Thresholds are zone-configurable via the backend config API. Defaults:

```text
Person detection:   0.70
Helmet detection:   0.75
Vest detection:     0.75
```

Detections below threshold are discarded without generating an event.

---

## Model Versioning

Models are versioned and stored in a model registry.

```text
models/
  rt-detr/
    v1.0/
    v1.1/   ← active
  ppe-classifier/
    v2.3/   ← active
```

Workers load the active model version on startup.

Hot-swap: the backend publishes a `ModelUpdated` event. Workers reload the new model without restarting the stream.

---

## RTSP Stream Resilience

Workers handle camera disconnections without crashing:

```text
Stream lost

↓

Retry: 5 seconds
Retry: 15 seconds
Retry: 60 seconds

↓ (still offline)

Publish CameraOfflineDetected event

↓

Backend creates alert

↓

Supervisor notified
```

Workers continue processing other cameras during retry.

---

## Circuit Breaker

If a worker fails repeatedly on a camera, it is isolated:

```text
3 consecutive processing failures

↓

Camera isolated from worker

↓

CameraOfflineDetected published

↓

Worker continues remaining cameras
```

---

## Worker ↔ Backend Config Sync — Race Condition Handling

A race condition can occur if a worker restarts at the same moment a config change event is published:

```text
Worker restarts

↓

Step 1: Pull latest config from backend REST API (authoritative source)

↓

Step 2: Subscribe to ConfigUpdated events

↓

Step 3: On ConfigUpdated, compare event version with local version

↓

If event version > local version → apply update
If event version <= local version → discard (already have latest)
```

Config versions are stored in `config.zone_configs.version` (integer, incremented on every update).

This ensures no config is missed during restarts and no duplicate updates are applied.

---

## AI Worker Metrics

Each worker exposes the following metrics to Prometheus:

```text
worker_frames_processed_total        ← total frames processed
worker_frames_dropped_total          ← frames dropped (queue overflow)
worker_inference_latency_seconds     ← per-frame inference time (histogram)
worker_detection_count_total         ← detections by type (helmet, vest, person)
worker_queue_depth                   ← current RabbitMQ publish queue depth
worker_camera_reconnect_total        ← camera reconnection attempts
worker_circuit_breaker_open_total    ← cameras isolated by circuit breaker
worker_heartbeat_timestamp           ← last heartbeat time (for liveness)
```

---

# Authentication & Authorization Architecture

## JWT Strategy

Authentication uses short-lived access tokens + long-lived refresh tokens.

```text
Login

↓

Access Token (JWT) — expires in 8 hours
Refresh Token (opaque, stored in DB) — expires in 7 days

↓

Client stores Access Token in memory (not localStorage)
Client stores Refresh Token in HttpOnly cookie
```

### Token Refresh Flow

```text
Access Token expires

↓

Client sends Refresh Token (via HttpOnly cookie)

↓

Backend validates Refresh Token against DB

↓

If valid → issue new Access Token + rotate Refresh Token

↓

Old Refresh Token is invalidated (rotation prevents replay attacks)
```

### Token Blacklisting on Logout

On logout:

```text
Client calls POST /api/v1/auth/logout

↓

Backend invalidates Refresh Token in DB (status = revoked)

↓

Access Token added to Redis blacklist with TTL = remaining token lifetime

↓

Every authenticated request checks Redis blacklist
```

This ensures that even if an Access Token is stolen, it cannot be used after logout.

---

## Role Based Access Control (RBAC)

Roles:

```text
Admin           → full access
Supervisor      → manage alerts, view cameras, view analytics
Safety Officer  → view alerts, view cameras
Viewer          → read-only dashboard
```

Permissions are stored as JSONB in `identity.roles.permissions` for flexibility.

Example:

```json
{
  "alerts": ["read", "acknowledge", "resolve"],
  "cameras": ["read"],
  "config": [],
  "audit": [],
  "users": []
}
```

Permission check happens in the API layer on every request. Unauthorized access returns `403 Forbidden` and is logged to `audit.audit_log`.

---

# WebSocket & Real-Time Architecture

## Why WebSocket Over Polling

Dashboard polling by 200 concurrent supervisors creates unnecessary load on the backend and database. WebSocket or SSE allows the backend to push updates only when data changes.

---

## Connection Manager

A centralized `WebSocketConnectionManager` handles all active connections in memory:

```text
ConnectionManager
  → connections: Dict[user_id, List[WebSocket]]

Methods:
  connect(user_id, websocket)
  disconnect(user_id, websocket)
  broadcast_to_user(user_id, message)
  broadcast_to_role(role, message)
  broadcast_to_all(message)
```

---

## Channels

```text
/ws/dashboard     ← occupancy updates, safety score, camera status
/ws/alerts        ← new alert notifications, status changes
```

---

## Scaling WebSocket Across Multiple Backend Instances

When backend scales to multiple instances, WebSocket connections are distributed across instances. A user connected to Instance A will not receive broadcasts from Instance B.

Solution: Redis Pub/Sub

```text
Backend Instance A receives AlertCreated event from RabbitMQ

↓

Instance A publishes to Redis channel: alerts:{role}

↓

All backend instances subscribe to Redis channels

↓

Each instance broadcasts to its own connected WebSocket clients
```

This ensures all connected clients receive alerts regardless of which backend instance they are connected to.

---

## Concurrent Connection Handling

Limits per role:

```text
Viewer:          5 concurrent WebSocket connections
Supervisor:      10 concurrent WebSocket connections
Safety Officer:  10 concurrent WebSocket connections
Admin:           20 concurrent WebSocket connections
```

Connections beyond the limit receive a `4008 Too Many Connections` close code.

---

# API Design & Versioning

## Versioning Strategy

All APIs are versioned via URL prefix:

```text
/api/v1/...
/api/v2/...   ← future breaking changes
```

### Breaking Change Policy

A breaking change is defined as:

* Removing or renaming a field in a response
* Changing the type of a field
* Removing an endpoint
* Changing required request parameters

Non-breaking changes (adding optional fields, adding new endpoints) are deployed without a version bump.

### Deprecation Policy

```text
Breaking change introduced in /api/v2/

↓

/api/v1/ endpoint marked deprecated
Deprecation-Notice header added to all v1 responses

↓

v1 maintained for 6 months

↓

v1 retired
```

### Version Headers

Every response includes:

```text
X-API-Version: v1
Deprecation: true   (only on deprecated endpoints)
Sunset: 2027-01-01  (date when endpoint will be removed)
```

---

# Caching Strategy

Redis is used as the primary cache layer.

## What is Cached

```text
Dashboard summary stats       → TTL: 30 seconds
Zone occupancy (latest)       → TTL: 10 seconds
Camera status list            → TTL: 15 seconds
User sessions / auth tokens   → TTL: matches token expiry
Active alert counts per zone  → TTL: 30 seconds
Pre-signed MinIO URLs         → TTL: matches URL expiry (15 minutes)
```

## Cache Invalidation Strategy

```text
Event received by backend consumer (e.g., OccupancyUpdated)

↓

Database updated

↓

Redis cache key invalidated immediately

↓

Next request fetches fresh data from DB and repopulates cache
```

Cache invalidation is event-driven, not time-based, for accuracy.

## Cache Keys

```text
dashboard:summary
zone:occupancy:{zone_id}
camera:status:all
alert:count:{zone_id}
snapshot:url:{snapshot_key}
```

---

# Database Architecture

Database: PostgreSQL

---

## Schema Strategy

```text
identity
factory
zone
camera
occupancy
ppe
alerts
notifications
analytics
reports
config
audit
```

---

## Core Tables

### identity.users

```text
Id
Name
Email
PasswordHash
RoleId              FK → identity.roles
Status
CreatedOn
LastLoginAt
```

### identity.roles

```text
Id
Name              (Admin, Supervisor, SafetyOfficer, Viewer)
Permissions       JSONB
```

### identity.refresh_tokens

```text
Id
UserId            FK → identity.users
TokenHash         (hashed, never store plaintext)
ExpiresAt
Status            (Active, Revoked)
CreatedAt
RevokedAt
```

### factory.factories

```text
Id
Name
Code
Location
Status
CreatedOn
```

### zone.zones

```text
Id
FactoryId
Name
MaxOccupancy
SupervisorId
Status
CreatedOn
```

### camera.cameras

```text
Id
ZoneId
Name
RTSPUrl
Status
LastSeenAt
WorkerId
CreatedOn
```

### config.zone_configs

```text
Id
ZoneId
PersonThreshold       DECIMAL
HelmetThreshold       DECIMAL
VestThreshold         DECIMAL
MaxOccupancy          INT
PPERequired           JSONB    (list of required PPE types)
UpdatedBy             FK → identity.users
UpdatedAt
Version               INT      ← incremented on every update (used for race-condition-safe sync)
```

Workers pull zone config on startup and subscribe to `ConfigUpdated` events. Version field is used to detect and discard stale updates.

### occupancy.logs

```text
Id
ZoneId
CameraId
CurrentCount
Timestamp
```

Partition by month. Retain 12 months online, archive older data to cold storage.

### ppe.violations

```text
Id
ZoneId
CameraId
ViolationType
Confidence
SnapshotKey           (object storage key, not local path)
CreatedOn
```

### alerts.alerts

```text
Id
ViolationId
Severity
Status              (Open, Acknowledged, Resolved)
AssignedTo          FK → identity.users
CreatedOn
ResolvedOn
```

### alerts.alert_history

```text
Id
AlertId
FromStatus
ToStatus
ChangedBy           FK → identity.users
ChangedAt
Comment
```

Tracks every status transition on an alert for compliance.

### notifications.notification_log

```text
Id
AlertId
Channel             (Email, InApp, Web)
RecipientId         FK → identity.users
SentAt
Status              (Sent, Failed, Delivered)
FailureReason
```

### audit.audit_log

```text
Id
UserId              FK → identity.users
Action              (AlertResolved, ConfigChanged, UserCreated, etc.)
EntityType
EntityId
OldValue            JSONB
NewValue            JSONB
IPAddress
Timestamp
```

All sensitive actions (alert resolution, config change, user management) are recorded here.

---

# Snapshot Storage Architecture

Violation snapshots are stored in an S3-compatible object store (MinIO for on-prem, AWS S3 for cloud).

Key format:

```text
snapshots/{zone_id}/{camera_id}/{timestamp}.jpg
```

The backend serves pre-signed URLs to the frontend for snapshot viewing. Snapshots are never served from local disk.

## Pre-Signed URL Strategy

```text
Frontend requests alert detail (includes snapshot_key)

↓

Backend checks Redis: snapshot:url:{snapshot_key}

↓ (cache miss)

Backend generates MinIO pre-signed URL with 15-minute expiry

↓

URL stored in Redis with TTL = 14 minutes (1 minute buffer before MinIO expiry)

↓

URL returned to frontend

↓ (cache hit)

Cached URL returned directly (no MinIO API call)
```

If a URL expires while the user has the page open, the frontend requests a new URL via a dedicated endpoint:

```text
GET /api/v1/snapshots/{snapshot_key}/url
→ Returns a fresh pre-signed URL
```

Retention:

```text
Active violations:   90 days online
Archived:            1 year cold storage
Purged:              after 1 year (configurable)
```

---

# Data Retention Policy

| Table | Online Retention | Archive | Purge |
|---|---|---|---|
| occupancy.logs | 12 months | 2 years cold | After 2 years |
| ppe.violations | 24 months | 3 years cold | After 3 years |
| alerts.alerts | 24 months | 3 years cold | After 3 years |
| audit.audit_log | 36 months | 5 years cold | After 5 years |
| snapshots | 90 days online | 1 year cold | After 1 year |
| identity.refresh_tokens | 7 days (auto-purged on expiry) | — | — |

Partitioning strategy: partition `occupancy.logs` and `ppe.violations` by month using PostgreSQL native partitioning.

---

# Dashboard Architecture

## Executive Dashboard

Displays:

* Total Cameras
* Active Alerts
* PPE Compliance
* Safety Score

Data source: cached Redis keys, refreshed via WebSocket push on change.

---

## Safety Dashboard

Displays:

* Violations
* Occupancy
* Open Alerts
* Alert resolution trend

---

## Camera Dashboard

Displays:

* Camera Health
* FPS
* Online Status
* Last seen timestamp
* Worker assignment

---

## Analytics Dashboard

Displays:

* Trends
* KPIs
* Monthly Reports
* Violation heatmap by zone

---

# API Rate Limiting

Rate limiting is applied at the backend per user and per role.

Default limits:

```text
Viewer:          60 requests/minute
Supervisor:      120 requests/minute
Safety Officer:  120 requests/minute
Admin:           300 requests/minute
```

Dashboard real-time updates use WebSocket to avoid polling overhead. Rate limiting does not apply to WebSocket connections (governed by connection limits per role instead).

Rate limit headers returned on every response:

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
```

On limit exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header.

---

# Security Architecture

## Authentication

* JWT Access Tokens — expire in 8 hours
* Refresh Token Rotation — single-use, rotated on every refresh
* Token Blacklisting via Redis on logout
* Refresh Tokens stored as hashed values in DB (never plaintext)

## Authorization

* Role Based Access Control (RBAC)
* Permissions stored as JSONB per role
* Permission check on every API request

## Transport Security

* HTTPS enforced in production
* WebSocket connections over WSS
* MinIO pre-signed URLs use HTTPS

## Input Validation

* All request bodies validated via Pydantic
* RTSP URL format validated before saving to DB
* File upload restricted to JPEG/PNG for snapshots

## Roles

```text
Admin
Supervisor
Safety Officer
Viewer
```

All sensitive actions are logged to `audit.audit_log`.

---

# Notification Architecture

Channels:

* Email
* In-App Notifications
* Web Push Notifications

All notifications are logged to `notifications.notification_log` for delivery tracking and debugging.

Flow:

```text
Violation

↓

Alert

↓

Notification (with delivery tracking)

↓

Supervisor (via Email + In-App + Web Push)
```

## Retry on Delivery Failure

```text
Notification send fails

↓

Status = Failed, FailureReason stored

↓

Background retry job: 3 attempts with exponential backoff

↓

If all retries fail → operations team alerted via audit log
```

---

# Zone Configuration Flow

Zone-level PPE rules and occupancy limits are managed in the backend and pushed to AI workers.

```text
Admin updates zone config via API

↓

Saved to config.zone_configs (version incremented)

↓

ConfigUpdated event published to RabbitMQ (includes new version number)

↓

AI workers subscribe to ConfigUpdated

↓

Worker compares event version with local version

↓

If newer → reload config for affected zone
If same or older → discard (stale event)

↓

No worker restart required
```

This ensures detection thresholds and PPE requirements can be changed at runtime without redeployment, and race conditions during worker restarts are safely handled via version comparison.

---

# Monitoring & Observability

## Prometheus Metrics

### Backend Metrics

```text
http_requests_total                    ← by endpoint, status code, method
http_request_duration_seconds          ← latency histogram by endpoint
active_websocket_connections           ← current live WebSocket connections
rabbitmq_events_consumed_total         ← by event type
rabbitmq_events_failed_total           ← events sent to DLQ
dlq_depth                              ← current DLQ message count
alert_created_total                    ← alerts created by type
alert_resolution_time_seconds          ← time from open to resolved
cache_hit_total                        ← Redis cache hits by key prefix
cache_miss_total                       ← Redis cache misses by key prefix
```

### AI Worker Metrics

```text
worker_frames_processed_total
worker_frames_dropped_total
worker_inference_latency_seconds       ← histogram (p50, p90, p99)
worker_detection_count_total           ← by detection type
worker_queue_depth
worker_camera_reconnect_total
worker_circuit_breaker_open_total
worker_heartbeat_timestamp
```

## Grafana Dashboards

```text
System Overview     ← API health, error rates, latency
AI Worker Health    ← per-worker frames, inference latency, queue depth
Alert Operations    ← alert volume, resolution time, open alerts by zone
Camera Health       ← online/offline counts, reconnection rate
DLQ Monitor         ← DLQ depth over time, failure reasons
```

## Loki (Log Aggregation)

All services ship structured JSON logs to Loki.

Log levels:

```text
ERROR   → alert-worthy failures
WARNING → degraded state (high DLQ depth, inference slowdown)
INFO    → normal operational events
DEBUG   → disabled in production
```

## Alerting Rules (Prometheus Alertmanager)

```text
DLQ depth > 100          → PagerDuty alert (operations)
Worker heartbeat missing → PagerDuty alert (operations)
API error rate > 5%      → PagerDuty alert (engineering)
Inference latency p99 > 2s → Slack alert (engineering)
Camera offline > 30s     → In-app alert (supervisor)
```

---

# Audit Trail

Every sensitive action is recorded in `audit.audit_log`:

* Alert acknowledged / resolved / reassigned
* Zone config changed
* User created / disabled
* Camera added / removed
* Role changed
* Unauthorized access attempt (403 responses)
* Logout (token revoked)

The audit log is immutable. No update or delete operations are permitted on audit records. Accessible only to Admin role.

---

# Deployment Architecture

## Development

```text
Laptop

React
FastAPI
PostgreSQL
RabbitMQ
Redis
MinIO (local object store)
AI Worker (CPU mode)
```

---

## Production (100 Cameras)

### Server 1

```text
React (served via Nginx)
FastAPI
PostgreSQL
RabbitMQ (with DLQ configured)
Redis
MinIO or S3
Prometheus + Grafana + Loki
```

### Server 2

```text
GPU Worker 1 (20 cameras)
```

### Server 3

```text
GPU Worker 2 (20 cameras)
```

### Server 4

```text
GPU Worker 3 (20 cameras)
```

### Server 5

```text
GPU Worker 4 (20 cameras)
```

---

# Scaling Strategy

## 100 Cameras

```text
1 Backend Server
4 AI Workers
```

---

## 200 Cameras

```text
2 Backend Servers (behind load balancer)
Redis Pub/Sub for WebSocket cross-instance broadcast
8 AI Workers
```

---

## 500 Cameras

```text
Backend Cluster (3–5 nodes)
Dedicated RabbitMQ Cluster
Dedicated PostgreSQL Cluster (primary + read replicas)
Redis Cluster
20+ AI Workers
Dedicated Object Storage Cluster
```

---

## 1000 Cameras

```text
API Gateway (Nginx / Kong)
Backend Cluster
RabbitMQ Cluster
PostgreSQL Cluster (primary + read replicas + connection pooler PgBouncer)
Redis Cluster
Object Storage Cluster
50+ AI Workers
Kubernetes for worker orchestration
```

No rewrite required. Only horizontal scaling.

---

# Technology Stack

Frontend:

* React
* TypeScript
* Material UI
* AG Grid

Backend:

* FastAPI
* SQLAlchemy
* Alembic

Database:

* PostgreSQL (with table partitioning)

Messaging:

* RabbitMQ (with Dead Letter Queue)

Cache:

* Redis (cache + pub/sub for WebSocket cross-instance broadcast)

Object Storage:

* MinIO (on-prem) / AWS S3 (cloud)

AI:

* OpenCV
* RT-DETR
* ByteTrack
* PyTorch

Monitoring:

* Prometheus
* Grafana
* Loki
* Alertmanager

Deployment:

* Docker
* Docker Compose

Future:

* Kubernetes (for 1000+ camera deployments)
* PgBouncer (PostgreSQL connection pooler at scale)

---

# Success Criteria

* 100 Cameras Supported
* Alert Latency < 5 Seconds
* Occupancy Accuracy > 95%
* PPE Accuracy > 90%
* Horizontal Scaling Supported
* Real-Time Dashboard (WebSocket-driven, no polling)
* Production Ready Architecture
* Zero data loss on worker crash (DLQ)
* Audit trail for all sensitive actions
* Zone config changes take effect without redeployment
* Snapshot retention policy enforced automatically
* Camera disconnection detected and alerted within 30 seconds
* Worker config race condition handled safely via version comparison
* Token blacklisting on logout prevents stolen token abuse
* WebSocket cross-instance broadcast via Redis Pub/Sub
* All metrics exported to Prometheus with Grafana dashboards
* Pre-signed snapshot URLs cached in Redis to reduce MinIO API calls

---

End of Document
