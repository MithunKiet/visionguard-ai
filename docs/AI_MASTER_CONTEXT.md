# VisionGuard AI — Master Context Document
## For AI Code Generation

Yeh document kisi bhi AI (ChatGPT, Claude, Gemini, Cursor, Copilot) ko dene ke liye hai taaki wo VisionGuard AI ka code generate kar sake bina kuch miss kiye.

---

# SECTION 1 — Project Identity

**Project Name:** VisionGuard AI
**Type:** Enterprise Factory Safety Monitoring & Compliance Platform
**Nature:** Real product — not a demo, not a portfolio project
**Deployment:** On-premise (factories), cloud-ready
**Clients:** Multiple enterprises (each with multiple factories)

## Critical Rules — NEVER Violate These

1. **NO hardcoded company names anywhere** — UI, emails, PDFs, filenames, code comments
2. **All branding is dynamic** — loaded from `enterprises` table at runtime
3. **AI Workers NEVER access database directly** — only publish RabbitMQ events
4. **Multi-tenant isolation** — every query scoped by `enterprise_id`
5. **Clean Architecture** — domain layer has zero dependency on framework/infra
6. **No module imports another module's infrastructure** — only interfaces
7. **Every sensitive action logged** to `audit.audit_log` (append-only)
8. **Config changes hot-apply** to AI workers via RabbitMQ — no restart needed
9. **Snapshots always stored in MinIO** — never on local disk
10. **Pre-signed URLs only** — never expose direct MinIO URLs to frontend

---

# SECTION 2 — Complete Hierarchy

```
Platform (VisionGuard AI)
    └── Enterprise          ← Client company (Tenant)
            └── Factory     ← Plant/Unit
                    └── Department  ← Production area group
                            └── Zone        ← Specific work area
                                    └── Camera  ← RTSP stream
```

**Key point:** Every DB table has `enterprise_id` column for tenant isolation.

---

# SECTION 3 — Technology Stack

## Backend
```
Language:      Python 3.11+
Framework:     FastAPI
ORM:           SQLAlchemy 2.0 (async)
Migrations:    Alembic
Validation:    Pydantic v2
Database:      PostgreSQL 16
Cache:         Redis
Message Queue: RabbitMQ (with Dead Letter Queue)
Object Store:  MinIO (S3-compatible)
Auth:          JWT (8h) + Refresh Tokens (7d, rotating)
```

## Frontend
```
Framework:     React 18 + TypeScript
Build:         Vite
UI Library:    Material UI (MUI)
State:         Zustand
Data Fetch:    TanStack Query (React Query)
Forms:         React Hook Form + Zod
Tables:        AG Grid Community
Charts:        Recharts
Router:        React Router v6
Real-time:     WebSocket (native)
```

## AI Worker
```
Language:      Python 3.11+
Detection:     YOLO (Ultralytics)
Tracking:      ByteTrack
Vision:        OpenCV
Runtime:       ONNX Runtime
GPU:           CUDA (auto-fallback to CPU)
```

## Infrastructure
```
Containers:    Docker + Docker Compose
Proxy:         Nginx
Monitoring:    Prometheus + Grafana + Loki
CI/CD:         GitHub Actions
```

---

# SECTION 4 — Complete Folder Structure

```
visionguard-ai/
│
├── backend/
│   ├── src/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── app.py              ← FastAPI app factory
│   │   │   ├── lifespan.py         ← startup/shutdown
│   │   │   ├── exceptions.py       ← global exception handlers
│   │   │   └── dependencies.py     ← shared DI
│   │   ├── shared/
│   │   │   ├── database/
│   │   │   │   ├── base.py         ← SQLAlchemy base model
│   │   │   │   ├── session.py      ← async session factory
│   │   │   │   └── mixins.py       ← SoftDelete, Audit, Version mixins
│   │   │   ├── cache/
│   │   │   │   ├── client.py       ← Redis client
│   │   │   │   └── helpers.py      ← get/set/delete/invalidate
│   │   │   ├── realtime/
│   │   │   │   └── manager.py      ← WebSocket connection manager
│   │   │   ├── messaging/
│   │   │   │   ├── consumer.py     ← RabbitMQ consumer
│   │   │   │   └── publisher.py    ← RabbitMQ publisher
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py         ← JWT middleware
│   │   │   │   ├── tenant.py       ← enterprise_id context setter
│   │   │   │   ├── ip_whitelist.py ← IP restriction
│   │   │   │   ├── rate_limit.py   ← Redis sliding window
│   │   │   │   ├── correlation.py  ← X-Correlation-ID
│   │   │   │   └── session.py      ← session timeout check
│   │   │   └── responses.py        ← standard response model
│   │   └── modules/
│   │       ├── identity/
│   │       ├── enterprise/
│   │       ├── factory/
│   │       ├── department/
│   │       ├── zone/
│   │       ├── camera/
│   │       ├── worker/
│   │       ├── occupancy/
│   │       ├── ppe/
│   │       ├── alerts/
│   │       ├── incidents/
│   │       ├── notifications/
│   │       ├── analytics/
│   │       ├── dashboard/
│   │       ├── reports/
│   │       ├── config/
│   │       ├── audit/
│   │       ├── health/
│   │       ├── shifts/
│   │       ├── maintenance/
│   │       ├── announcements/
│   │       └── api_keys/
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── ai-worker/
│   ├── src/
│   │   ├── main.py
│   │   ├── pipeline/
│   │   │   ├── camera_worker.py    ← per-camera processing loop
│   │   │   ├── frame_reader.py     ← RTSP capture + reconnect
│   │   │   ├── detector.py         ← YOLO inference
│   │   │   ├── tracker.py          ← ByteTrack integration
│   │   │   ├── ppe_validator.py    ← PPE rule evaluation
│   │   │   ├── occupancy_counter.py← person count per zone
│   │   │   └── rules_engine.py     ← configurable violation rules
│   │   ├── events/
│   │   │   └── publisher.py        ← RabbitMQ event publisher
│   │   ├── config/
│   │   │   ├── settings.py         ← env vars
│   │   │   └── zone_sync.py        ← config pull + hot-reload
│   │   └── health/
│   │       └── metrics.py          ← Prometheus metrics
│   ├── models/                     ← YOLO model weights (gitignored)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── store/                  ← Zustand stores
│   │   ├── api/                    ← TanStack Query hooks
│   │   ├── types/                  ← TypeScript interfaces
│   │   ├── hooks/                  ← custom hooks
│   │   ├── utils/                  ← helpers
│   │   ├── pages/
│   │   │   ├── Auth/               ← Login, ChangePassword
│   │   │   ├── SetupWizard/        ← First-time onboarding
│   │   │   ├── Dashboard/          ← Executive, Safety, Zone, Camera
│   │   │   ├── Alerts/             ← List, Detail, Bulk actions
│   │   │   ├── Incidents/
│   │   │   ├── Cameras/
│   │   │   ├── Analytics/
│   │   │   ├── Reports/
│   │   │   ├── Config/
│   │   │   ├── Shifts/
│   │   │   ├── Maintenance/
│   │   │   ├── Announcements/
│   │   │   └── Admin/              ← Users, Roles, Factories, Zones
│   │   └── components/
│   │       ├── Layout/
│   │       ├── Charts/
│   │       ├── Tables/
│   │       ├── Forms/
│   │       └── Common/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
│
├── infra/
│   ├── nginx/
│   │   └── nginx.conf
│   ├── prometheus/
│   │   └── prometheus.yml
│   ├── grafana/
│   │   └── dashboards/
│   └── loki/
│       └── loki-config.yml
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATABASE.md
│   └── DEPLOYMENT.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
│
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── README.md
└── IMPLEMENTATION.md
```

---

# SECTION 5 — Clean Architecture Per Module

Every module MUST follow this exact structure:

```
module_name/
├── api/
│   ├── routes.py           ← FastAPI router, endpoints, WebSocket
│   ├── request_models.py   ← Pydantic input schemas
│   └── response_models.py  ← Pydantic output schemas
│
├── application/
│   ├── commands/           ← Write operations (Create, Update, Delete)
│   │   └── create_xxx.py
│   ├── queries/            ← Read operations (Get, List)
│   │   └── get_xxx.py
│   └── services/           ← Orchestration (calls domain + infra)
│
├── domain/
│   ├── entities.py         ← Core business objects (pure Python)
│   ├── value_objects.py    ← Immutable domain concepts
│   ├── events.py           ← Domain events
│   ├── repositories.py     ← Repository interfaces (ABC)
│   └── rules.py            ← Business rule validation
│
├── infrastructure/
│   ├── models.py           ← SQLAlchemy ORM models
│   ├── repositories.py     ← Concrete repo implementations
│   └── external/           ← Third-party integrations
│
└── tests/
    ├── unit/
    └── integration/
```

**CRITICAL RULES:**
- `domain/` has ZERO imports from SQLAlchemy, FastAPI, Redis, RabbitMQ
- `api/` imports from `application/` only
- `application/` imports from `domain/` and `infrastructure/` via interfaces
- Cross-module calls via interfaces only — never import another module's `infrastructure/`

---

# SECTION 6 — Database Schema

## All Tables Must Have These Columns (via mixin)
```python
class AuditMixin:
    created_on  = Column(DateTime(timezone=True), default=func.now())
    created_by  = Column(UUID, ForeignKey('identity.users.id'), nullable=True)
    modified_on = Column(DateTime(timezone=True), onupdate=func.now())
    modified_by = Column(UUID, ForeignKey('identity.users.id'), nullable=True)
    version     = Column(Integer, default=1)        # optimistic locking
    deleted_at  = Column(DateTime(timezone=True))   # soft delete
    enterprise_id = Column(UUID, ForeignKey('enterprises.id'), nullable=False)
```

## Core Tables

### enterprises
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
name            VARCHAR(200) NOT NULL
code            VARCHAR(50) UNIQUE NOT NULL
logo_url        VARCHAR(500)
favicon_url     VARCHAR(500)
primary_color   VARCHAR(7) DEFAULT '#1565C0'
secondary_color VARCHAR(7) DEFAULT '#42A5F5'
tagline         VARCHAR(300)
industry        VARCHAR(100)
contact_person  VARCHAR(200)
contact_email   VARCHAR(200)
status          VARCHAR(20) DEFAULT 'Active'   -- Active/Inactive/Suspended
created_on      TIMESTAMPTZ DEFAULT NOW()
```

### identity.users
```sql
id                  UUID PRIMARY KEY
enterprise_id       UUID REFERENCES enterprises(id)
name                VARCHAR(200)
email               VARCHAR(200) UNIQUE
password_hash       VARCHAR(500)
role                VARCHAR(50)   -- HO_ADMIN/FACTORY_ADMIN/DEPT_HEAD/SAFETY_OFFICER/SUPERVISOR/VIEWER
factory_id          UUID REFERENCES factories(id) NULLABLE
department_id       UUID REFERENCES departments(id) NULLABLE
assigned_zone_ids   UUID[]        -- for Supervisor role
status              VARCHAR(20) DEFAULT 'Active'
is_first_login      BOOLEAN DEFAULT TRUE
setup_completed     BOOLEAN DEFAULT FALSE
password_changed_at TIMESTAMPTZ
totp_enabled        BOOLEAN DEFAULT FALSE
dnd_enabled         BOOLEAN DEFAULT FALSE
dnd_start           TIME
dnd_end             TIME
notification_prefs  JSONB         -- {"Critical":["Email","InApp"],"High":["InApp"]}
session_timeout_min INT           -- per-user override
last_login_at       TIMESTAMPTZ
invited_by          UUID REFERENCES identity.users(id)
```

### factories
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID REFERENCES enterprises(id) NOT NULL
name            VARCHAR(200)
code            VARCHAR(50)
location        VARCHAR(300)
plant_head_id   UUID REFERENCES identity.users(id)
status          VARCHAR(20) DEFAULT 'Active'
-- + AuditMixin columns
```

### departments
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID REFERENCES enterprises(id) NOT NULL
factory_id      UUID REFERENCES factories(id) NOT NULL
name            VARCHAR(200)
code            VARCHAR(50)
head_user_id    UUID REFERENCES identity.users(id)
status          VARCHAR(20) DEFAULT 'Active'
-- + AuditMixin columns
```

### zones
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID REFERENCES enterprises(id) NOT NULL
factory_id      UUID REFERENCES factories(id) NOT NULL
department_id   UUID REFERENCES departments(id) NOT NULL
name            VARCHAR(200)
code            VARCHAR(50)
max_occupancy   INT NOT NULL
supervisor_id   UUID REFERENCES identity.users(id)
zone_type       VARCHAR(50)    -- Production/Storage/Restricted/Entry-Exit
is_restricted   BOOLEAN DEFAULT FALSE
status          VARCHAR(20) DEFAULT 'Active'
-- + AuditMixin columns
```

### cameras
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID REFERENCES enterprises(id) NOT NULL
factory_id      UUID REFERENCES factories(id) NOT NULL
zone_id         UUID REFERENCES zones(id) NOT NULL
name            VARCHAR(200)
code            VARCHAR(50)
rtsp_url        VARCHAR(500)    -- encrypted at rest
camera_type     VARCHAR(50)     -- Fixed/PTZ/Fisheye
position_desc   VARCHAR(300)
status          VARCHAR(20) DEFAULT 'Active'   -- Online/Offline/Degraded/Maintenance
fps             DECIMAL(5,2)
last_seen_at    TIMESTAMPTZ
worker_id       UUID REFERENCES worker.ai_workers(id)
in_maintenance  BOOLEAN DEFAULT FALSE
maintenance_until TIMESTAMPTZ
-- + AuditMixin columns
```

### config.zone_configs
```sql
id                  UUID PRIMARY KEY
enterprise_id       UUID REFERENCES enterprises(id) NOT NULL
zone_id             UUID REFERENCES zones(id) UNIQUE NOT NULL
person_threshold    DECIMAL(4,2) DEFAULT 0.70
helmet_threshold    DECIMAL(4,2) DEFAULT 0.75
vest_threshold      DECIMAL(4,2) DEFAULT 0.75
gloves_threshold    DECIMAL(4,2) DEFAULT 0.70
shoes_threshold     DECIMAL(4,2) DEFAULT 0.70
mask_threshold      DECIMAL(4,2) DEFAULT 0.75
max_occupancy       INT
frame_sample_fps    INT DEFAULT 2
ppe_required        JSONB DEFAULT '["helmet","vest"]'
cooldown_seconds    INT DEFAULT 120
updated_by          UUID REFERENCES identity.users(id)
updated_at          TIMESTAMPTZ
version             INT DEFAULT 1   -- CRITICAL: increment on every save
```

### config.zone_rules
```sql
id                  UUID PRIMARY KEY
enterprise_id       UUID REFERENCES enterprises(id) NOT NULL
zone_id             UUID REFERENCES zones(id) NOT NULL
rule_name           VARCHAR(200)
condition_type      VARCHAR(100)  -- HELMET_MISSING/VEST_MISSING/OVERCROWDING/etc.
duration_seconds    INT DEFAULT 3
cooldown_seconds    INT DEFAULT 120
severity            VARCHAR(20)   -- Critical/High/Medium/Low
enabled             BOOLEAN DEFAULT TRUE
actions             JSONB  -- ["CREATE_ALERT","STORE_SNAPSHOT","NOTIFY"]
notify_roles        JSONB  -- ["Supervisor","SafetyOfficer"]
notify_channels     JSONB  -- ["Email","InApp","WebPush"]
created_by          UUID REFERENCES identity.users(id)
created_on          TIMESTAMPTZ DEFAULT NOW()
```

### occupancy.logs (PARTITIONED BY MONTH)
```sql
id              UUID DEFAULT gen_random_uuid()
enterprise_id   UUID NOT NULL
zone_id         UUID REFERENCES zones(id)
camera_id       UUID REFERENCES cameras(id)
current_count   INT
shift_id        UUID REFERENCES shifts(id)
timestamp       TIMESTAMPTZ NOT NULL
-- Partition: PARTITION BY RANGE (timestamp)
```

### ppe.violations (PARTITIONED BY MONTH)
```sql
id              UUID DEFAULT gen_random_uuid()
enterprise_id   UUID NOT NULL
zone_id         UUID REFERENCES zones(id)
camera_id       UUID REFERENCES cameras(id)
violation_type  VARCHAR(50)   -- HELMET_MISSING/VEST_MISSING/GLOVES_MISSING/etc.
confidence      DECIMAL(5,4)
snapshot_key    VARCHAR(500)  -- MinIO object key
track_id        VARCHAR(100)  -- ByteTrack ID
shift_id        UUID REFERENCES shifts(id)
rule_id         UUID REFERENCES config.zone_rules(id)
is_false_positive BOOLEAN DEFAULT FALSE
fp_reason       VARCHAR(200)
created_on      TIMESTAMPTZ NOT NULL
-- Partition: PARTITION BY RANGE (created_on)
```

### alerts.alerts
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
factory_id      UUID REFERENCES factories(id)
department_id   UUID REFERENCES departments(id)
zone_id         UUID REFERENCES zones(id)
camera_id       UUID REFERENCES cameras(id)
violation_id    UUID REFERENCES ppe.violations(id) NULLABLE
alert_number    VARCHAR(30) UNIQUE  -- ALT-2026-0001
alert_type      VARCHAR(100)
severity        VARCHAR(20)
status          VARCHAR(30) DEFAULT 'Open'
assigned_to     UUID REFERENCES identity.users(id)
shift_id        UUID REFERENCES shifts(id)
sla_due_at      TIMESTAMPTZ
created_on      TIMESTAMPTZ DEFAULT NOW()
acknowledged_on TIMESTAMPTZ
resolved_on     TIMESTAMPTZ
created_by      VARCHAR(100)  -- 'system' or user_id
```

### alerts.alert_history
```sql
id          UUID PRIMARY KEY
alert_id    UUID REFERENCES alerts.alerts(id)
from_status VARCHAR(30)
to_status   VARCHAR(30)
changed_by  UUID REFERENCES identity.users(id)
changed_at  TIMESTAMPTZ DEFAULT NOW()
comment     TEXT
```

### notifications.notification_log
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
alert_id        UUID REFERENCES alerts.alerts(id)
channel         VARCHAR(30)   -- Email/InApp/WebPush/Slack/Teams/Webhook/SMS
recipient_id    UUID REFERENCES identity.users(id)
sent_at         TIMESTAMPTZ
status          VARCHAR(20)   -- Sent/Delivered/Failed
failure_reason  TEXT
retry_count     INT DEFAULT 0
```

### audit.audit_log (IMMUTABLE — NO UPDATE/DELETE)
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
enterprise_id   UUID NOT NULL
user_id         UUID REFERENCES identity.users(id)
action          VARCHAR(100)
entity_type     VARCHAR(100)
entity_id       UUID
old_value       JSONB
new_value       JSONB
ip_address      VARCHAR(50)
user_agent      TEXT
correlation_id  VARCHAR(100)
timestamp       TIMESTAMPTZ DEFAULT NOW()
```

### shifts
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
factory_id      UUID REFERENCES factories(id)
name            VARCHAR(100)   -- Morning Shift
start_time      TIME
end_time        TIME
days            JSONB          -- ["MON","TUE","WED","THU","FRI","SAT"]
status          VARCHAR(20) DEFAULT 'Active'
```

### camera_maintenance
```sql
id                  UUID PRIMARY KEY
enterprise_id       UUID NOT NULL
camera_id           UUID REFERENCES cameras(id)
scheduled_date      DATE
maintenance_type    VARCHAR(50)
assigned_to         UUID REFERENCES identity.users(id)
status              VARCHAR(30) DEFAULT 'Scheduled'
notes               TEXT
completed_at        TIMESTAMPTZ
completed_by        UUID REFERENCES identity.users(id)
completion_notes    TEXT
next_due_date       DATE
```

### config_history
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
zone_id         UUID REFERENCES zones(id)
changed_by      UUID REFERENCES identity.users(id)
old_config      JSONB
new_config      JSONB
change_reason   TEXT
changed_at      TIMESTAMPTZ DEFAULT NOW()
```

### config_templates
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
name            VARCHAR(200)
description     TEXT
config_data     JSONB
created_by      UUID REFERENCES identity.users(id)
created_on      TIMESTAMPTZ DEFAULT NOW()
```

### announcements
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
factory_id      UUID REFERENCES factories(id) NULLABLE
department_id   UUID REFERENCES departments(id) NULLABLE
title           VARCHAR(300)
message         TEXT
priority        VARCHAR(20) DEFAULT 'Normal'
scope           VARCHAR(30)   -- Enterprise/Factory/Department
expires_at      TIMESTAMPTZ
created_by      UUID REFERENCES identity.users(id)
created_on      TIMESTAMPTZ DEFAULT NOW()
```

### api_keys
```sql
id              UUID PRIMARY KEY
enterprise_id   UUID NOT NULL
name            VARCHAR(200)
key_hash        VARCHAR(500)   -- SHA-256
permissions     JSONB
expires_at      TIMESTAMPTZ
last_used_at    TIMESTAMPTZ
status          VARCHAR(20) DEFAULT 'Active'
created_by      UUID REFERENCES identity.users(id)
created_on      TIMESTAMPTZ DEFAULT NOW()
```

### onboarding.setup_progress
```sql
id                  UUID PRIMARY KEY
user_id             UUID REFERENCES identity.users(id)
enterprise_id       UUID REFERENCES enterprises(id)
last_completed_step INT DEFAULT 0
factory_id          UUID NULLABLE
department_id       UUID NULLABLE
zone_id             UUID NULLABLE
camera_id           UUID NULLABLE
completed_at        TIMESTAMPTZ
```

---

# SECTION 7 — All RabbitMQ Events

## AI Worker → Backend (ai_worker_events exchange)

| Event | Routing Key | Publisher |
|---|---|---|
| OccupancyUpdated | events.occupancy_updated | AI Worker |
| HelmetMissingDetected | events.helmet_missing_detected | AI Worker |
| VestMissingDetected | events.vest_missing_detected | AI Worker |
| GlovesMissingDetected | events.gloves_missing_detected | AI Worker |
| ShoesMissingDetected | events.shoes_missing_detected | AI Worker |
| MaskMissingDetected | events.mask_missing_detected | AI Worker |
| OvercrowdingDetected | events.overcrowding_detected | AI Worker |
| UnauthorizedEntryDetected | events.unauthorized_entry_detected | AI Worker |
| CameraOfflineDetected | events.camera_offline_detected | AI Worker |
| CameraReconnected | events.camera_reconnected | AI Worker |
| WorkerHeartbeat | events.worker_heartbeat | AI Worker |

## Backend → AI Worker (config_events exchange)

| Event | Routing Key | Publisher |
|---|---|---|
| ConfigUpdated | config.zone_config_updated | Backend |
| ModelUpdated | config.model_updated | Backend |
| CamerasAssigned | config.worker_cameras_updated | Backend |

## Event Payload Structure
```json
{
  "event":          "helmet_missing_detected",
  "event_id":       "uuid-v4",
  "enterprise_id":  "uuid",
  "factory_id":     "uuid",
  "zone_id":        "uuid",
  "camera_id":      "uuid",
  "worker_id":      "worker-1",
  "timestamp":      "2026-01-01T10:00:00Z",
  "confidence":     0.91,
  "track_id":       "T-042",
  "snapshot_key":   "snapshots/zone-id/cam-id/2026-01-01T10-00-00.jpg",
  "shift_id":       "uuid",
  "config_version": 7
}
```

---

# SECTION 8 — API Structure

## Standard Response Format
```json
{
  "success": true,
  "data": { },
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 145,
    "total_pages": 8
  },
  "error": null
}
```

## Error Response Format
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ALERT_NOT_FOUND",
    "message": "Alert not found",
    "details": {}
  }
}
```

## All API Endpoints

```
# Auth
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
POST   /api/v1/auth/change-password
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password
POST   /api/v1/auth/2fa/enable
POST   /api/v1/auth/2fa/verify
POST   /api/v1/auth/2fa/disable

# Enterprise (HO Admin only)
GET    /api/v1/enterprise/dashboard
GET    /api/v1/enterprise/analytics
GET    /api/v1/enterprise/branding
PUT    /api/v1/enterprise/branding
POST   /api/v1/enterprise/branding/logo

# Factories
GET    /api/v1/factories
POST   /api/v1/factories
GET    /api/v1/factories/{id}
PUT    /api/v1/factories/{id}
DELETE /api/v1/factories/{id}
GET    /api/v1/factories/{id}/dashboard

# Departments
GET    /api/v1/departments
POST   /api/v1/departments
GET    /api/v1/departments/{id}
PUT    /api/v1/departments/{id}
DELETE /api/v1/departments/{id}
GET    /api/v1/departments/{id}/dashboard

# Zones
GET    /api/v1/zones
POST   /api/v1/zones
GET    /api/v1/zones/{id}
PUT    /api/v1/zones/{id}
DELETE /api/v1/zones/{id}

# Cameras
GET    /api/v1/cameras
POST   /api/v1/cameras
GET    /api/v1/cameras/{id}
PUT    /api/v1/cameras/{id}
DELETE /api/v1/cameras/{id}
GET    /api/v1/cameras/{id}/health
POST   /api/v1/cameras/{id}/snapshot
POST   /api/v1/cameras/{id}/maintenance/enable
POST   /api/v1/cameras/{id}/maintenance/complete
POST   /api/v1/cameras/test-connection
POST   /api/v1/cameras/bulk-import

# Workers
GET    /api/v1/workers
GET    /api/v1/workers/{id}
GET    /api/v1/workers/{id}/metrics

# Alerts
GET    /api/v1/alerts
GET    /api/v1/alerts/{id}
PATCH  /api/v1/alerts/{id}/acknowledge
PATCH  /api/v1/alerts/{id}/resolve
PATCH  /api/v1/alerts/{id}/assign
PATCH  /api/v1/alerts/{id}/false-positive
PATCH  /api/v1/alerts/{id}/snooze
POST   /api/v1/alerts/bulk-action

# Incidents
GET    /api/v1/incidents
GET    /api/v1/incidents/{id}
PATCH  /api/v1/incidents/{id}/close

# Occupancy
GET    /api/v1/occupancy/current
GET    /api/v1/occupancy/history

# Analytics
GET    /api/v1/analytics/violations
GET    /api/v1/analytics/occupancy
GET    /api/v1/analytics/compliance
GET    /api/v1/analytics/safety-score
GET    /api/v1/analytics/shifts
GET    /api/v1/analytics/comparative

# Reports
POST   /api/v1/reports/generate
GET    /api/v1/reports
GET    /api/v1/reports/{id}/download
GET    /api/v1/reports/scheduled
POST   /api/v1/reports/scheduled
PUT    /api/v1/reports/scheduled/{id}

# Config
GET    /api/v1/config/zone/{zone_id}
PUT    /api/v1/config/zone/{zone_id}
GET    /api/v1/config/zone/{zone_id}/history
POST   /api/v1/config/zone/{zone_id}/restore
POST   /api/v1/config/zone/{zone_id}/copy
GET    /api/v1/config/templates
POST   /api/v1/config/templates
POST   /api/v1/config/templates/{id}/apply
POST   /api/v1/config/bulk-update
GET    /api/v1/config/rules
POST   /api/v1/config/rules
PUT    /api/v1/config/rules/{id}

# Users
GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{id}
PUT    /api/v1/users/{id}
PATCH  /api/v1/users/{id}/status
POST   /api/v1/users/bulk-import
GET    /api/v1/users/groups
POST   /api/v1/users/groups

# Shifts
GET    /api/v1/shifts
POST   /api/v1/shifts
PUT    /api/v1/shifts/{id}
GET    /api/v1/shifts/active

# Maintenance
GET    /api/v1/maintenance
POST   /api/v1/maintenance
GET    /api/v1/maintenance/{id}
PATCH  /api/v1/maintenance/{id}/complete

# Announcements
GET    /api/v1/announcements
POST   /api/v1/announcements
POST   /api/v1/announcements/{id}/read

# API Keys
GET    /api/v1/api-keys
POST   /api/v1/api-keys
DELETE /api/v1/api-keys/{id}

# Audit
GET    /api/v1/audit

# Setup (Wizard)
GET    /api/v1/setup/progress
POST   /api/v1/setup/factory
POST   /api/v1/setup/department
POST   /api/v1/setup/zone
POST   /api/v1/setup/camera
POST   /api/v1/setup/complete

# Snapshots
GET    /api/v1/snapshots/{key}/url

# Health
GET    /health/live
GET    /health/ready
GET    /health/status

# WebSocket
WS     /ws/dashboard
WS     /ws/alerts
```

---

# SECTION 9 — User Roles & Scope

| Role | enterprise_id scope | factory_id scope | Notes |
|---|---|---|---|
| SUPER_ADMIN | All (bypasses RLS) | All | VisionGuard team only |
| HO_ADMIN | Own enterprise | All factories | Cross-factory view |
| FACTORY_ADMIN | Own enterprise | Own factory only | |
| DEPT_HEAD | Own enterprise | Own factory | Own department only |
| SAFETY_OFFICER | Own enterprise | Own factory | All zones in factory |
| SUPERVISOR | Own enterprise | Own factory | Assigned zones only |
| VIEWER | Own enterprise | Assigned scope | Read-only |

---

# SECTION 10 — Authentication Flow

```
Login → Access Token (JWT, 8h) + Refresh Token (opaque, 7d, HttpOnly cookie)
     → is_first_login=true → Force password change
     → setup_completed=false + HO_ADMIN → Redirect to Setup Wizard
     → Normal → Dashboard

Token Refresh → Old refresh token revoked → New pair issued
Logout → Refresh token revoked in DB + Access token JTI in Redis blacklist
2FA → TOTP via Google Authenticator → Mandatory for SUPER_ADMIN + HO_ADMIN
Session → Redis key with TTL per role → Frontend keepalive ping every 5 min
```

---

# SECTION 11 — AI Worker Critical Rules

1. Workers NEVER access PostgreSQL directly
2. Workers ONLY publish to RabbitMQ
3. On startup: pull config from REST API first, then subscribe to config events
4. Config version check: event.version > local_version → apply, else discard
5. Camera reconnect: retry 5s → 15s → 60s → publish CameraOfflineDetected
6. Circuit breaker: 3 failures → isolate camera → continue other cameras
7. Frame sampling: default 2 FPS from 25 FPS (configurable per zone)
8. Snapshot: capture on violation → upload to MinIO → include key in event
9. Snooze check: before publishing any alert event, check Redis snooze key
10. Maintenance check: before publishing any event, check Redis maintenance key
11. Heartbeat: publish WorkerHeartbeat every 30 seconds
12. Model hot-swap: on ModelUpdated event → swap without restarting streams
13. CLAHE preprocessing: apply Contrast Limited Adaptive Histogram Equalization on every frame before YOLO inference — improves accuracy in low-light, glare, and flickering conditions
14. Multi-frame voting: require 3 consecutive positive frames before publishing a violation event — eliminates motion-blur and occlusion false alarms. Reset count to 0 on any clean frame.
15. Fine-tuned model required: NEVER use COCO-pretrained weights in production. Model must be fine-tuned on factory-specific PPE dataset (500–2,000 labeled images per class minimum)
16. Low-confidence handling: if detection confidence is below zone threshold but above a floor (e.g. 0.40), publish a `LowConfidenceViolation` review event instead of a hard alert — human supervisor reviews the snapshot

```python
# Rule 13 — CLAHE preprocessing (apply before every YOLO call)
import cv2, numpy as np

def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = cv2.merge([clahe.apply(l), a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

# Rule 14 — Multi-frame voting
REQUIRED_CONSECUTIVE_FRAMES = 3   # configurable per zone

class ViolationTracker:
    _counts: Dict[str, int] = {}

    def record(self, track_id: str, violation: bool) -> bool:
        self._counts[track_id] = (self._counts.get(track_id, 0) + 1) if violation else 0
        return self._counts[track_id] >= REQUIRED_CONSECUTIVE_FRAMES

# Rule 16 — Low-confidence routing
def route_detection(confidence: float, zone_config: ZoneConfig) -> str:
    if confidence >= zone_config.helmet_threshold:
        return "violation"        # publish hard alert event
    elif confidence >= 0.40:
        return "review"           # publish LowConfidenceViolation event
    else:
        return "ignore"
```

---

# SECTION 12 — WebSocket Events (Backend → Frontend)

Channel: `/ws/dashboard`
```json
{"type": "occupancy_updated",     "zone_id": "...", "count": 6, "max": 5}
{"type": "camera_status_changed", "camera_id": "...", "status": "Offline"}
{"type": "safety_score_updated",  "factory_id": "...", "score": 91.2}
{"type": "activity_feed",         "message": "Alert resolved by ...", "timestamp": "..."}
```

Channel: `/ws/alerts`
```json
{"type": "alert_created",      "alert": {...}}
{"type": "alert_acknowledged", "alert_id": "...", "by": "..."}
{"type": "alert_resolved",     "alert_id": "...", "by": "..."}
{"type": "alert_escalated",    "alert_id": "...", "level": 2}
```

---

# SECTION 13 — MinIO Storage Structure

```
Buckets:
  snapshots/
    {enterprise_id}/{factory_id}/{zone_id}/{camera_id}/{YYYY-MM-DD}/{HH-MM-SS}.jpg

  logos/
    {enterprise_id}/logo.png
    {enterprise_id}/favicon.ico

  reports/
    {enterprise_id}/{YYYY-MM}/{report_id}.pdf
    {enterprise_id}/{YYYY-MM}/{report_id}.xlsx

  models/
    yolo/v1.0/weights.onnx
    yolo/v1.1/weights.onnx   ← active
```

---

# SECTION 14 — Onboarding Flow Summary

```
Super Admin → Create Enterprise → Create HO Admin
HO Admin → First Login → Force Password Change
         → is_first_login=false, setup_completed=false
         → Redirect to Setup Wizard

Setup Wizard:
  Step 1: Create Factory   → POST /api/v1/setup/factory
  Step 2: Create Dept      → POST /api/v1/setup/department
  Step 3: Create Zone      → POST /api/v1/setup/zone (+ PPE config)
  Step 4: Add Camera       → POST /api/v1/setup/camera (+ RTSP test)
  Complete                 → POST /api/v1/setup/complete
                           → setup_completed=true
                           → Auto-assign AI workers
                           → Redirect to Dashboard
```

---

# SECTION 15 — Dynamic Branding Rules

NEVER hardcode any company name, logo, or color in:
- React components
- Email templates
- PDF templates
- Export filenames
- Code comments (example values ok, actual names never)

Always load from:
```typescript
// Frontend — on app load
const enterprise = await api.get('/api/v1/enterprise/branding')
// Use everywhere:
enterprise.name         // company name
enterprise.logo_url     // pre-signed MinIO URL
enterprise.primary_color // CSS variable
enterprise.code         // for export filenames: `${enterprise.code}_report.pdf`
```

---

# SECTION 16 — Key Non-Functional Requirements

| Requirement | Target |
|---|---|
| Alert latency (detect → notify) | ≤ 5 seconds |
| API response time (p95) | ≤ 200ms |
| WebSocket push latency | ≤ 1 second |
| Camera offline detection | ≤ 60 seconds |
| Config propagation to workers | ≤ 10 seconds |
| System availability | 99.5% |
| Helmet detection accuracy | ≥ 90% |
| Occupancy count accuracy | ≥ 95% |
| False positive rate | ≤ 5% |
| Test coverage | ≥ 80% |

---

# SECTION 17 — What To Generate Phase-by-Phase

## IMPORTANT: Vertical Slice Gate (Must Pass Before Any Module Build)

Before generating any full module, generate and validate the vertical slice:

```
RTSP Camera → YOLO (with CLAHE + multi-frame voting) → RabbitMQ PPEViolationDetected
    → Backend consumer → PostgreSQL → WebSocket push → React dashboard alert
```

**Gate criteria (must all pass on real hardware before proceeding):**
- RTSP stream stable at target FPS
- YOLO inference ≥ 10 FPS per stream
- End-to-end alert latency ≤ 5 seconds
- Helmet accuracy ≥ 85% on actual factory camera footage

Only after the vertical slice passes do full module builds begin.

---

## Business Delivery Phases (Value-First Order)

### Business Phase 1 — Core Safety MVP (~8 weeks)
Scope: Only what a supervisor needs on Day 1.

**Modules to generate:**
- `identity` — Auth, JWT, RBAC (no 2FA yet, add in Phase 2)
- `camera` — Camera registry, RTSP health check
- `worker` — AI worker registry, heartbeat
- `ppe` — PPE violation records
- `occupancy` — Real-time occupancy tracking
- `alerts` — Alert create → acknowledge → close (no escalation yet)
- `notifications` — Email + In-App only
- `dashboard` — Supervisor WebSocket dashboard

**DO NOT generate in Phase 1:** announcements, api_keys, maintenance, shifts, reports, analytics, audit, config templates, 2FA, IP whitelisting, dynamic branding, escalation engine.

**Phase 1 Gate:**
- 1 real camera stream running end-to-end
- PPE violation detected → alert created → supervisor notified < 5s
- API test coverage ≥ 80% for Phase 1 modules

### Business Phase 2 — Operations (~6 weeks)

**Modules to generate:**
- `config` — Zone config hot-swap, history, templates
- `shifts` — Shift management + violation tagging
- `maintenance` — Camera maintenance mode
- `audit` — Immutable audit trail
- `notifications` — Add SMS, Slack, Teams, webhooks
- `identity` — Add 2FA, IP whitelisting
- `reports` — PDF/Excel export
- `alerts` — Add escalation engine, snooze, bulk actions

**Phase 2 Gate:**
- 10 cameras running simultaneously
- Zone config changed at runtime, AI worker picks up within 30s
- Audit log records all sensitive actions

### Business Phase 3 — Enterprise (~6 weeks)

**Modules to generate:**
- `enterprise` — Multi-tenant isolation, dynamic branding
- `analytics` — KPIs, heatmaps, shift analytics
- `reports` — Scheduled, comparative reports
- `api_keys` — Client API access
- `announcements` — Notice board
- `onboarding` — Setup wizard

**Phase 3 Gate:**
- Multi-tenant isolation verified (enterprise A cannot see enterprise B data)
- 50 cameras stable at target hardware spec
- System availability ≥ 99.5% over 7-day soak test

---

## Technical Generation Order (within each business phase)

### Tech Phase 1 — Foundation (generate first, within Business Phase 1)
- docker-compose.yml (all services)
- docker-compose.prod.yml
- .env.example (all variables)
- backend/src/main.py
- backend/src/core/ (app factory, lifespan, exceptions)
- backend/src/shared/ (database, cache, messaging, middleware, responses)
- Alembic setup + base migration

### Tech Phase 2 — Identity & Auth
- Full identity module (Clean Architecture)
- JWT + Refresh Token + Blacklisting
- Session timeout
- RBAC middleware
- Tenant context middleware
- *(2FA and IP Whitelist middleware: defer to Business Phase 2)*

### Tech Phase 3 — Core Business Modules (Business Phase 1 scope)
- camera, worker, ppe, occupancy, alerts (basic), notifications (email+inapp), dashboard modules
- Vertical slice validation

### Tech Phase 4 — AI Worker (Business Phase 1 scope)
- Full AI worker with CLAHE preprocessing + multi-frame voting + fine-tuned model loading
- YOLO + ByteTrack + Rules Engine
- RTSP reconnect + circuit breaker
- RabbitMQ publisher
- Config sync (race-condition safe)
- Model hot-swap
- Prometheus metrics

### Tech Phase 5 — Operations Modules (Business Phase 2)
- config, shifts, maintenance, audit modules
- Escalation engine, alert snooze, bulk actions
- Extended notifications (SMS, Slack, Teams, webhooks)
- 2FA, IP Whitelist middleware

### Tech Phase 6 — Enterprise Modules (Business Phase 3)
- enterprise (multi-tenant, branding), analytics, reports
- api_keys, announcements, onboarding/setup wizard

### Tech Phase 7 — Frontend
- All pages (listed in folder structure)
- WebSocket integration
- Dynamic branding
- Setup Wizard UI
- Real-time dashboard

### Tech Phase 8 — Infrastructure
- Nginx config
- Prometheus + Grafana + Loki
- GitHub Actions CI/CD

### Tech Phase 9 — Tests
- Unit tests per module
- Integration tests
- API tests
- AI pipeline tests (including CLAHE + multi-frame voting unit tests)

---

# SECTION 18 — Camera Placement Requirements (Installation Spec)

Bad camera placement degrades accuracy more than a bad model. These are mandatory pre-installation requirements. Generate onboarding wizard copy and installation docs using these values.

| Parameter | Requirement | Reason |
|---|---|---|
| Camera height | 3 – 5 meters | Lower = occlusion; higher = too small to detect PPE |
| Tilt angle | 30° – 45° downward | Flat angle misses helmet tops; steep angle loses face/vest |
| Zone overlap | ≥ 15% overlap between adjacent cameras | Eliminates blind spots at zone edges |
| Resolution | Minimum 1080p @ 15 FPS | Below this, YOLO accuracy drops significantly |
| Lighting | ≥ 150 LUX in monitored zone | Below this, CLAHE helps but accuracy still suffers |
| IR / Night Vision | Required for any zone running 24/7 shifts | Standard cameras fail below 50 LUX |
| Lens type | Wide-angle (2.8mm–4mm) for large zones | Telephoto for narrow/deep zones only |
| Camera type | Fixed preferred; PTZ only for entry/exit gates | PTZ tracking adds latency and complexity |

**In Setup Wizard Step 4 (Camera):** Show this checklist before the user submits camera RTSP URL. Add a `placement_confirmed: boolean` field to the camera creation form.

---

# SECTION 19 — Prompt Template for AI

When giving this context to another AI, use this prompt:

```
You are a Senior Software Architect and Full-Stack Engineer.

Read the attached AI_MASTER_CONTEXT.md completely before writing any code.

Follow these rules strictly:
1. No hardcoded company names anywhere
2. Clean Architecture — every module has api/application/domain/infrastructure/tests
3. AI Workers never touch the database
4. Multi-tenant isolation via enterprise_id on every query
5. Generate production-quality code — no TODO, no placeholder
6. Include proper error handling, logging, type hints
7. Follow the exact folder structure in Section 4
8. Use the exact DB schema in Section 6
9. Implement tenant middleware that sets enterprise_id context
10. Every endpoint must check user's scope (role-based filtering)
11. AI Worker must use CLAHE preprocessing on every frame before YOLO inference
12. AI Worker must use multi-frame voting (3 consecutive frames) before publishing any violation event
13. Never use COCO-pretrained YOLO weights — model must be factory fine-tuned
14. Follow phased delivery — generate only Business Phase 1 modules unless told otherwise
15. Validate vertical slice end-to-end before expanding to full module list

Now generate: [SPECIFIC PHASE OR MODULE]
```

---

# SECTION 20 — Common Mistakes to Avoid

| Mistake | Correct Approach |
|---|---|
| Hardcoding company name | Load from `enterprise.name` DB field |
| AI worker calling PostgreSQL | Publish RabbitMQ event only |
| Missing enterprise_id on query | Always filter by enterprise_id |
| Cross-module infra import | Use interfaces / domain events |
| Raw SQL queries | SQLAlchemy ORM always |
| Skipping audit log | Every sensitive action must be logged |
| Hardcoding thresholds | Load from config.zone_configs |
| Ignoring config version | Check version before applying config update |
| Alert on snoozed camera | Check Redis snooze key first |
| Alert during maintenance | Check Redis maintenance key first |
| Direct MinIO URL | Always pre-signed URL with TTL |
| Password in plaintext | bcrypt hash always |
| Refresh token in response body | HttpOnly cookie only |
| Missing soft delete | All tables have deleted_at column |
| Using COCO-pretrained YOLO in production | Fine-tune on factory PPE dataset first (500–2,000 images per class) |
| Alerting on single-frame detection | Multi-frame vote required (3 consecutive frames) before publishing event |
| Running YOLO on raw frames | Apply CLAHE preprocessing on every frame before inference |
| Building all 24 modules at once | Follow phased delivery — MVP 8 modules first, gate review before next phase |
| Skipping vertical slice validation | Prove end-to-end pipeline on real hardware before full module build |

---

*End of AI Master Context Document*
*VisionGuard AI — Enterprise Factory Safety Monitoring Platform*
