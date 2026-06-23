# IMPLEMENTATION.md

# VisionGuard AI

## Enterprise Factory Safety Monitoring Platform

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
                 │
                 ▼
┌────────────────────────────────────┐
│          FastAPI Backend           │
│      Modular Monolith Core         │
│      API Rate Limiting             │
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

Responsibilities:

* Authentication
* Business Rules
* Alert Processing
* Analytics
* Reporting
* Dashboard APIs
* API Rate Limiting (per user / per role)

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

* PostgreSQL
* RabbitMQ (with Dead Letter Queue)
* Redis
* Object Storage (S3-compatible)
* External Services

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
Version               INT
```

Workers pull zone config on startup and subscribe to `ConfigUpdated` events.

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

Partitioning strategy: partition `occupancy.logs` and `ppe.violations` by month using PostgreSQL native partitioning.

---

# Dashboard Architecture

## Executive Dashboard

Displays:

* Total Cameras
* Active Alerts
* PPE Compliance
* Safety Score

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

Dashboard polling endpoints use server-sent events (SSE) or WebSockets to avoid polling overhead.

Rate limit headers returned on every response:

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
```

---

# Security Architecture

Authentication: JWT

Authorization: Role Based Access Control

Roles:

* Admin
* Supervisor
* Safety Officer
* Viewer

All sensitive actions are logged to `audit.audit_log`.

JWT tokens expire after 8 hours. Refresh tokens valid for 7 days.

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

Supervisor
```

---

# Zone Configuration Flow

Zone-level PPE rules and occupancy limits are managed in the backend and pushed to AI workers.

```text
Admin updates zone config via API

↓

Saved to config.zone_configs

↓

ConfigUpdated event published to RabbitMQ

↓

AI workers subscribe to ConfigUpdated

↓

Workers reload config for affected zone

↓

No worker restart required
```

This means detection thresholds and PPE requirements can be changed at runtime without redeployment.

---

# Audit Trail

Every sensitive action is recorded in `audit.audit_log`:

* Alert acknowledged / resolved / reassigned
* Zone config changed
* User created / disabled
* Camera added / removed
* Role changed

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
AI Worker
```

---

## Production (100 Cameras)

### Server 1

```text
React
FastAPI
PostgreSQL
RabbitMQ (with DLQ configured)
Redis
MinIO or S3
```

### Server 2

```text
GPU Worker 1
```

### Server 3

```text
GPU Worker 2
```

### Server 4

```text
GPU Worker 3
```

### Server 5

```text
GPU Worker 4
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
2 Backend Servers
8 AI Workers
```

---

## 500 Cameras

```text
Backend Cluster
Dedicated RabbitMQ Cluster
Dedicated PostgreSQL Cluster
20+ AI Workers
Dedicated Object Storage Cluster
```

---

## 1000 Cameras

```text
API Gateway
Backend Cluster
RabbitMQ Cluster
PostgreSQL Cluster
Redis Cluster
Object Storage Cluster
50+ AI Workers
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

* Redis

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

Deployment:

* Docker
* Docker Compose

Future:

* Kubernetes

---

# Success Criteria

* 100 Cameras Supported
* Alert Latency < 5 Seconds
* Occupancy Accuracy > 95%
* PPE Accuracy > 90%
* Horizontal Scaling Supported
* Real-Time Dashboard
* Production Ready Architecture
* Zero data loss on worker crash (DLQ)
* Audit trail for all sensitive actions
* Zone config changes take effect without redeployment
* Snapshot retention policy enforced automatically
* Camera disconnection detected and alerted within 30 seconds

---

End of Document
