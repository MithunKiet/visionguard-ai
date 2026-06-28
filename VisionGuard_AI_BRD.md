# VisionGuard AI
## Business Requirements Document (BRD)
### Enterprise Factory Safety Monitoring & Compliance Platform
### Version 2.0 — Extended Enterprise Edition

---

# Document Control

| Field | Value |
|---|---|
| Document Title | VisionGuard AI — Business Requirements Document |
| Version | 2.0 |
| Status | Final |
| Project Name | VisionGuard AI |
| Project Type | AI-Powered Factory Safety Monitoring Platform |
| Deployment Model | On-Premise (Cloud-ready) |
| Platform | Web-Based |
| Prepared For | Factory Management · Safety Department · IT Department |
| Target Users | Plant Admin · Safety Officers · Supervisors · Security · Viewers |
| Initial Capacity | 50 Cameras · 1 Factory |
| Future Capacity | 1000+ Cameras · 100+ Factories |

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Business Challenges](#2-current-business-challenges)
3. [Gap Analysis — BRD v1.0 vs Enterprise Edition](#3-gap-analysis)
4. [Proposed Solution](#4-proposed-solution)
5. [Business Goals & KPIs](#5-business-goals--kpis)
6. [System Scope](#6-system-scope)
7. [Factory & Organizational Structure](#7-factory--organizational-structure)
8. [User Roles & Permissions](#8-user-roles--permissions)
9. [Functional Requirements — All Modules](#9-functional-requirements--all-modules)
10. [Business Rules](#10-business-rules)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [AI & Detection Requirements](#12-ai--detection-requirements)
13. [Security Requirements](#13-security-requirements)
14. [Reporting Requirements](#14-reporting-requirements)
15. [Notification Requirements](#15-notification-requirements)
16. [Integration Requirements](#16-integration-requirements)
17. [Hardware Requirements](#17-hardware-requirements)
18. [Workflow Scenarios](#18-workflow-scenarios)
19. [Success Criteria](#19-success-criteria)
20. [Future Roadmap](#20-future-roadmap)

---

# 1. Executive Summary

Factory safety monitoring in manufacturing environments is currently a manual, reactive process. Supervisors and safety officers physically patrol production floors to verify PPE compliance, monitor zone occupancy, and identify unauthorized access. This approach is slow, error-prone, produces no audit evidence, and cannot scale.

**VisionGuard AI** replaces this manual process with an AI-powered, real-time monitoring platform. The system connects to existing factory CCTV cameras via RTSP, analyzes video feeds using computer vision models, detects violations automatically, and alerts the right people instantly — all from a centralized web dashboard.

The platform is designed as a **production-ready enterprise system** — not a demo or prototype. It must support real factory deployments from day one, with a clear scaling path from 1 factory and 50 cameras to 100 factories and 1000+ cameras.

---

# 2. Current Business Challenges

## 2.1 Problem 1 — PPE Non-Compliance

Workers frequently enter production zones without required Personal Protective Equipment.

**Affected PPE Types:**
- Safety Helmet (Hard Hat)
- Safety Vest (High-visibility)
- Safety Gloves
- Safety Shoes / Steel-toe boots
- Face Mask (in applicable zones)

**Current Detection Method:** Manual observation by supervisors and safety officers.

**Problems with Current Method:**

| Problem | Impact |
|---|---|
| Human error in observation | Violations missed regularly |
| Delayed detection | Worker already in danger zone |
| No photographic evidence | Disputes during incident investigation |
| No audit trail | Compliance audits fail |
| No trend data | Cannot identify repeat offenders or high-risk zones |
| No automated alerts | Supervisor must be physically present |

**Business Impact:**
- Regulatory fines from labor safety authorities
- Increased workplace injury rate
- Higher insurance premiums
- Failed factory safety audits

---

## 2.2 Problem 2 — Zone Overcrowding

Production zones have defined occupancy limits for safety reasons. These limits are regularly exceeded without anyone noticing.

**Example Zone Limits:**

| Zone | Max Capacity | Risk if Exceeded |
|---|---|---|
| Welding Area | 5 | Fire hazard, reduced visibility |
| Paint Shop | 3 | Fume inhalation risk |
| Boiler Area | 2 | Explosion risk |
| Chemical Storage | 1 | Contamination risk |
| Assembly Line | 10 | Collision risk |
| Packaging Area | 8 | Ergonomic injury risk |

**Problems:**
- No real-time person count per zone
- No automatic alert when limit exceeded
- Safety risk accumulates silently
- No historical data on peak occupancy patterns

---

## 2.3 Problem 3 — Delayed Incident Response

Incidents are reported after they occur — often hours later — by which time evidence is lost and response is reactive.

**Examples:**
- Worker fall — discovered only when worker does not return
- Unauthorized entry — discovered during manual review of footage
- PPE violation — reported after a near-miss incident
- Camera offline — discovered during next scheduled maintenance

**Impact:**
- Management receives information too late to prevent harm
- No chain of custody for evidence
- Compliance investigations lack supporting data

---

## 2.4 Problem 4 — No Centralized Monitoring

Most factories have existing CCTV systems but:
- No centralized dashboard to view all cameras
- No AI analytics layer
- No alert automation
- No occupancy tracking
- Multiple disconnected systems (CCTV, access control, HR) with no integration
- No historical trend analysis

---

## 2.5 Problem 5 — Compliance & Audit Readiness (Gap — Not in BRD v1.0)

Factories undergo periodic safety audits by regulatory bodies. Currently:
- No structured audit trail of safety events
- No exportable compliance reports
- No evidence of corrective actions taken
- No documentation of alert resolution workflows

---

## 2.6 Problem 6 — No Safety Performance Measurement (Gap — Not in BRD v1.0)

Factory management has no objective safety KPIs:
- Cannot measure PPE compliance rate over time
- Cannot compare safety performance between zones or shifts
- Cannot identify safety improvement or degradation trends
- No safety score to drive improvement programs

---

# 3. Gap Analysis

## BRD v1.0 → Enterprise Edition v2.0

| Area | BRD v1.0 | Enterprise v2.0 | Gap Filled |
|---|---|---|---|
| PPE Detection | Helmet + Vest only | Helmet + Vest + Gloves + Shoes + Mask | ✅ |
| Occupancy | Basic count | Count + peak tracking + heatmap + shift analysis | ✅ |
| Alerts | Basic alert | Full lifecycle: Open → Ack → InProgress → Closed + history | ✅ |
| Roles | 4 roles | 4 roles + granular per-module permissions | ✅ |
| Notifications | Not specified | Email + In-App + Web Push + Slack + Teams + Webhook | ✅ |
| Multi-Factory | Single factory | Multi-factory with organization-level isolation | ✅ |
| Analytics | Basic % | KPIs + trends + heatmaps + safety score + shift analysis | ✅ |
| Reports | Not specified | PDF + Excel, scheduled + on-demand | ✅ |
| Security | JWT + RBAC | JWT + refresh rotation + blacklisting + OWASP + audit | ✅ |
| AI Pipeline | Not specified | YOLO + ByteTrack + Rules Engine + hot-swap | ✅ |
| Camera Health | Offline alert | FPS + latency + circuit breaker + reconnect policy | ✅ |
| Audit Trail | Not specified | Immutable append-only audit log, compliance export | ✅ |
| Monitoring | Not specified | Prometheus + Grafana + Loki + Alertmanager | ✅ |
| Scalability | 50→200 cameras | 50→1000+ cameras, multi-factory, horizontal scaling | ✅ |
| Rules Engine | Hardcoded | Fully configurable, DB-driven, duration-aware | ✅ |
| Deployment | Not specified | Docker + Nginx + CI/CD + prod compose | ✅ |
| Integrations | Listed as future | API-ready stubs for SAP, HRMS, SMS, Fire Alarm | ✅ |
| Worker Tracking | Not specified | AI worker registry, heartbeat, camera assignment | ✅ |

---

# 4. Proposed Solution

VisionGuard AI will:

1. Connect to all factory RTSP cameras
2. Process video streams in real time using AI (YOLO + ByteTrack)
3. Detect PPE violations, overcrowding, and unauthorized entry automatically
4. Evaluate violations against configurable business rules
5. Generate alerts and route them to the right supervisors
6. Store violation snapshots as evidence
7. Provide a real-time web dashboard for all stakeholders
8. Maintain complete historical records for compliance
9. Provide analytics, trends, and safety KPIs
10. Send notifications via multiple channels instantly
11. Generate compliance reports on demand
12. Support scaling from 1 to 100+ factories without re-architecture

---

# 5. Business Goals & KPIs

## Business Goals

| Goal | Metric | Target |
|---|---|---|
| Reduce PPE violations | PPE violation count | -80% within 6 months |
| Reduce safety incidents | Incident count per month | -50% within 12 months |
| Improve alert response | Alert acknowledgement time | < 5 minutes |
| Improve audit readiness | Audit findings | Zero evidence gaps |
| Real-time monitoring | Dashboard latency | < 5 seconds |
| System reliability | Camera uptime monitoring | 99.5% availability |

## Operational KPIs

| KPI | Formula | Frequency |
|---|---|---|
| Helmet Compliance % | (Compliant frames / Total person frames) × 100 | Daily |
| Vest Compliance % | (Compliant frames / Total person frames) × 100 | Daily |
| Overall PPE Compliance % | Average of all PPE KPIs | Daily |
| Safety Score | 0.6 × PPE% + 0.3 × (1 − incident rate) + 0.1 × closure speed | Weekly |
| Alert Response Time | avg(acknowledged_on − created_on) | Daily |
| Alert Closure Time | avg(resolved_on − created_on) | Daily |
| Peak Occupancy | max(current_count) per zone per day | Daily |
| Overcrowding Frequency | Count of overcrowding events per zone | Weekly |
| Camera Uptime % | (Online minutes / Total minutes) × 100 | Daily |
| Incident Rate | Incidents per 1000 person-hours | Monthly |

---

# 6. System Scope

## In Scope

- Real-time RTSP camera stream processing
- PPE detection: Helmet, Vest, Gloves, Shoes, Mask
- Occupancy monitoring and zone capacity enforcement
- Unauthorized zone entry detection
- Camera health monitoring (online/offline/FPS/latency)
- Configurable business rules and alert routing
- Multi-channel notification delivery
- Real-time web dashboard with WebSocket push
- Historical analytics and trend reporting
- Compliance report generation (PDF + Excel)
- Immutable audit trail
- Role-based access control
- Multi-factory, multi-organization support
- AI model versioning and hot-swap
- Docker-based deployment

## Out of Scope (Phase 1)

- Face recognition / worker identity
- Mobile application (native iOS/Android)
- Edge AI processing (on-camera inference)
- Fire and smoke detection
- Fall detection
- Forklift/vehicle detection
- Predictive analytics / AI risk scoring
- SAP / HRMS integration (API stubs only)
- Biometric access control

---

# 7. Factory & Organizational Structure

## Hierarchy

```
Organization (Tenant)
    └── Factory (Plant)
            └── Zone (Production Area)
                    └── Camera (RTSP Stream)
```

## Example

```
Organization: ABC Manufacturing Ltd.

├── Factory: Greater Noida Plant
│     ├── Zone: Assembly Area        (Max: 10 people) [3 cameras]
│     ├── Zone: Welding Area         (Max: 5 people)  [2 cameras]
│     ├── Zone: Paint Shop           (Max: 3 people)  [2 cameras]
│     ├── Zone: Packaging Area       (Max: 8 people)  [2 cameras]
│     ├── Zone: Warehouse            (Max: 15 people) [3 cameras]
│     ├── Zone: Dispatch Area        (Max: 6 people)  [2 cameras]
│     ├── Zone: Chemical Storage     (Max: 1 person)  [1 camera]
│     ├── Zone: Boiler Area          (Max: 2 people)  [1 camera]
│     └── Zone: Loading Dock         (Max: 4 people)  [2 cameras]
│
└── Factory: Pune Plant
      ├── Zone: CNC Machining        (Max: 8 people)  [2 cameras]
      └── Zone: Quality Control      (Max: 6 people)  [2 cameras]
```

---

# 8. User Roles & Permissions

## Role Definitions

### Role 1 — Plant Admin

**Scope:** Full access to assigned factories.

**Responsibilities:**
- Manage factory structure (zones, cameras)
- Manage users and assign roles
- Configure detection rules per zone
- View all dashboards, alerts, analytics
- Generate and export compliance reports
- Access audit logs
- Manage AI worker assignments
- Configure notification templates

**Permissions:**

| Module | Create | Read | Update | Delete |
|---|---|---|---|---|
| Factory | ✅ | ✅ | ✅ | ✅ |
| Zone | ✅ | ✅ | ✅ | ✅ |
| Camera | ✅ | ✅ | ✅ | ✅ |
| Users | ✅ | ✅ | ✅ | ✅ |
| Alerts | ✅ | ✅ | ✅ | ✅ |
| Config | ✅ | ✅ | ✅ | ✅ |
| Reports | ✅ | ✅ | — | — |
| Audit | — | ✅ | — | — |
| Analytics | — | ✅ | — | — |

---

### Role 2 — Safety Officer

**Scope:** All zones in assigned factory.

**Responsibilities:**
- Monitor all alerts and violations
- Investigate incidents with snapshot evidence
- Acknowledge and resolve alerts
- Generate safety compliance reports
- View analytics and trends
- View audit logs for their actions

**Permissions:**

| Module | Create | Read | Update | Delete |
|---|---|---|---|---|
| Factory | — | ✅ | — | — |
| Zone | — | ✅ | — | — |
| Camera | — | ✅ | — | — |
| Alerts | — | ✅ | ✅ (ack/resolve) | — |
| Reports | ✅ | ✅ | — | — |
| Analytics | — | ✅ | — | — |
| Audit | — | ✅ (own actions) | — | — |

---

### Role 3 — Supervisor

**Scope:** Assigned zones only.

**Responsibilities:**
- Monitor assigned zones in real time
- Acknowledge and resolve alerts for assigned zones
- Take corrective actions and log comments
- View zone-level dashboard

**Permissions:**

| Module | Create | Read | Update | Delete |
|---|---|---|---|---|
| Zone (assigned) | — | ✅ | — | — |
| Camera (assigned) | — | ✅ | — | — |
| Alerts (assigned zones) | — | ✅ | ✅ (ack/resolve) | — |
| Analytics (zone) | — | ✅ | — | — |

---

### Role 4 — Viewer

**Scope:** Read-only access to assigned dashboards.

**Responsibilities:**
- View dashboards assigned by admin
- No alert management capability
- Typically used for plant managers, executives, auditors

**Permissions:**

| Module | Create | Read | Update | Delete |
|---|---|---|---|---|
| Dashboard | — | ✅ | — | — |
| Alerts | — | ✅ | — | — |
| Analytics | — | ✅ | — | — |

---

# 9. Functional Requirements — All Modules

---

## Module 1 — Identity & Access Management

### 1.1 User Registration & Management

**FR-IAM-001:** Admin shall be able to create users with the following fields:
- Full Name
- Email Address (unique, used as login)
- Role (Admin / Safety Officer / Supervisor / Viewer)
- Assigned Factory
- Assigned Zones (for Supervisor role)
- Status (Active / Inactive)

**FR-IAM-002:** Admin shall be able to activate, deactivate, or suspend user accounts.

**FR-IAM-003:** System shall send a welcome email to newly created users with a one-time password setup link.

**FR-IAM-004:** Users shall be able to update their own profile (name, password, notification preferences).

### 1.2 Authentication

**FR-IAM-005:** System shall authenticate users via email + password.

**FR-IAM-006:** System shall issue a JWT Access Token (8-hour expiry) and a Refresh Token (7-day expiry) on successful login.

**FR-IAM-007:** System shall implement Refresh Token Rotation — each refresh issues a new token and invalidates the old one.

**FR-IAM-008:** System shall blacklist Access Tokens on logout using Redis TTL.

**FR-IAM-009:** System shall detect and prevent Refresh Token replay attacks — reuse of a revoked token triggers full session invalidation.

**FR-IAM-010:** System shall support password reset via email OTP.

**FR-IAM-011:** System shall enforce password policy: minimum 8 characters, at least 1 uppercase, 1 number, 1 special character.

**FR-IAM-012:** System shall lock account after 5 consecutive failed login attempts for 15 minutes.

### 1.3 Authorization

**FR-IAM-013:** System shall enforce Role-Based Access Control (RBAC) on every API endpoint.

**FR-IAM-014:** Unauthorized access attempts shall return HTTP 403 and be logged to audit.

**FR-IAM-015:** Permissions shall be stored per role as JSONB for flexibility.

**FR-IAM-016:** Supervisors shall only access alerts and dashboards for their assigned zones.

---

## Module 2 — Organization Management

### 2.1 Organization

**FR-ORG-001:** System shall support multi-tenant organizations.

**FR-ORG-002:** Each organization shall have complete data isolation from other organizations.

**FR-ORG-003:** Organization fields:
- Organization Name
- Organization Code (unique)
- Industry Type
- Contact Person
- Contact Email
- Status (Active / Inactive)
- Subscription Plan (future)

**FR-ORG-004:** System Admin (super-user) shall manage organizations. Organization-level Admin manages factories within their org.

---

## Module 3 — Factory Management

### 3.1 Factory CRUD

**FR-FAC-001:** Admin shall create factories with:
- Factory Name
- Factory Code (unique within org)
- Address
- City / State / Country
- Plant Head (linked user)
- GPS Coordinates (optional, for reporting)
- Status (Active / Inactive)

**FR-FAC-002:** Admin shall edit factory details and status.

**FR-FAC-003:** Deleting a factory shall be a soft delete — all historical data retained.

**FR-FAC-004:** Factory list shall be searchable, filterable by status, and paginated.

**FR-FAC-005:** Factory dashboard shall show:
- Total zones
- Total cameras (online / offline)
- Active alerts count
- Today's violations count
- PPE compliance % (today)
- Safety score

---

## Module 4 — Zone Management

### 4.1 Zone CRUD

**FR-ZON-001:** Admin shall create zones within a factory with:
- Zone Name
- Zone Code (unique within factory)
- Description
- Max Occupancy (integer)
- Supervisor (linked user)
- Zone Type (Production / Storage / Restricted / Entry-Exit / Office)
- Restricted Zone flag (boolean — triggers unauthorized entry alerts)
- Status (Active / Inactive)

**FR-ZON-002:** Admin shall assign multiple cameras to a zone.

**FR-ZON-003:** Admin shall assign a supervisor to a zone. Supervisors receive alerts only for their assigned zones.

**FR-ZON-004:** Zone list shall show current occupancy vs max occupancy with color indicators:
- Green: < 70% capacity
- Yellow: 70–90% capacity
- Red: > 90% capacity or exceeded

**FR-ZON-005:** Soft delete only — zones with historical data cannot be hard deleted.

### 4.2 Zone Configuration

**FR-ZON-006:** Admin shall configure per-zone detection settings:
- Person detection confidence threshold
- Helmet detection confidence threshold
- Vest detection confidence threshold
- Gloves detection confidence threshold
- Shoes detection confidence threshold
- Mask detection confidence threshold
- Required PPE list (checkboxes)
- Max occupancy override (same as FR-ZON-001 but can be updated live)
- Frame sampling rate (FPS to process)
- Violation cooldown period (minimum seconds between same violation alerts)

**FR-ZON-007:** Config changes shall take effect in AI workers within 10 seconds without restarting streams.

**FR-ZON-008:** Config version number shall increment on every save (used for race-condition-safe sync with AI workers).

---

## Module 5 — Camera Management

### 5.1 Camera CRUD

**FR-CAM-001:** Admin shall register cameras with:
- Camera Name
- Camera Code (unique within factory)
- RTSP URL (encrypted at rest)
- Zone assignment
- Camera Type (Fixed / PTZ / Fisheye)
- Position Description (e.g., "North wall, facing main entry")
- Status (Active / Inactive)

**FR-CAM-002:** Admin shall update camera details including RTSP URL.

**FR-CAM-003:** System shall validate RTSP URL format before saving.

**FR-CAM-004:** Camera list shall show:
- Camera name and code
- Zone assignment
- Online / Offline / Degraded status
- Current FPS
- Last seen timestamp
- Assigned AI worker

### 5.2 Camera Health Monitoring

**FR-CAM-005:** System shall monitor each camera's health in real time:
- Online / Offline status
- Stream FPS (live)
- Stream latency
- Last frame timestamp
- Reconnection attempt count

**FR-CAM-006:** Camera shall be marked Offline if no frame received for 60 seconds.

**FR-CAM-007:** Camera shall be marked Degraded if FPS drops below 50% of expected rate.

**FR-CAM-008:** AI workers shall attempt automatic reconnection:
- Retry 1: after 5 seconds
- Retry 2: after 15 seconds
- Retry 3: after 60 seconds
- After 3 failures: publish CameraOfflineDetected event

**FR-CAM-009:** Circuit breaker: 3 consecutive processing failures on same camera → camera isolated → CameraOfflineDetected published.

---

## Module 6 — AI Worker Management

### 6.1 Worker Registry

**FR-WRK-001:** System shall maintain a registry of all AI worker instances with:
- Worker ID (unique)
- Worker Name
- Host IP / Hostname
- Status (Online / Offline / Degraded)
- Assigned cameras (list)
- Current model version
- GPU / CPU mode
- Last heartbeat timestamp
- Frames processed (total)

**FR-WRK-002:** Workers shall publish heartbeat events every 30 seconds.

**FR-WRK-003:** Worker shall be marked offline if no heartbeat received for 90 seconds.

**FR-WRK-004:** Admin shall view worker health dashboard showing all workers and their assigned cameras.

**FR-WRK-005:** Admin shall be able to trigger camera reassignment between workers (future Phase 2 — auto-rebalancing).

### 6.2 Model Management

**FR-WRK-006:** Admin shall upload new AI model versions via the backend API.

**FR-WRK-007:** New model versions shall be stored in MinIO model registry.

**FR-WRK-008:** Backend shall publish ModelUpdated event to trigger hot-swap on all workers.

**FR-WRK-009:** Workers shall swap the model without restarting camera streams.

**FR-WRK-010:** Each worker shall report its active model version in heartbeat events.

---

## Module 7 — Occupancy Monitoring

### 7.1 Real-Time Occupancy

**FR-OCC-001:** System shall count persons in each zone in real time using AI detection + ByteTrack tracking.

**FR-OCC-002:** Occupancy count shall be updated every time a detection frame is processed (default every 500ms at 2 FPS).

**FR-OCC-003:** Dashboard shall show live occupancy per zone updated via WebSocket.

**FR-OCC-004:** Occupancy gauge shall use color coding:
- Green: 0 to 70% of max
- Yellow: 70% to 100% of max
- Red: Exceeded max

**FR-OCC-005:** IF current_count > max_occupancy THEN generate OvercrowdingDetected event → create High severity alert.

**FR-OCC-006:** Overcrowding alert shall not re-trigger within a configurable cooldown period (default: 2 minutes).

### 7.2 Occupancy History

**FR-OCC-007:** System shall log occupancy readings every minute to `occupancy.logs`.

**FR-OCC-008:** System shall track peak occupancy per zone per day.

**FR-OCC-009:** Analytics shall show:
- Average occupancy by hour (heatmap)
- Peak occupancy by day
- Overcrowding frequency by zone
- Occupancy trend (7-day, 30-day)

---

## Module 8 — PPE Detection

### 8.1 Detection Types

**FR-PPE-001: Helmet Detection**

System shall detect presence or absence of safety helmet on each detected person.

Detection states:
- Helmet Present ✅
- Helmet Missing ❌

Rule:
```
IF person_detected AND helmet_missing
FOR >= 3 seconds (sustained violation)
THEN create violation + store snapshot + generate alert
```

---

**FR-PPE-002: Safety Vest Detection**

System shall detect presence or absence of high-visibility safety vest.

Detection states:
- Vest Present ✅
- Vest Missing ❌

Rule:
```
IF person_detected AND vest_missing
FOR >= 3 seconds
THEN create violation + store snapshot + generate alert
```

---

**FR-PPE-003: Gloves Detection**

System shall detect presence or absence of safety gloves.

Applicable zones: Welding Area, Chemical Storage, CNC Machining.

Rule:
```
IF zone.requires_gloves AND person_detected AND gloves_missing
FOR >= 5 seconds
THEN create violation + store snapshot + generate alert
```

---

**FR-PPE-004: Safety Shoes Detection**

System shall detect presence or absence of safety shoes / steel-toe boots.

Rule:
```
IF zone.requires_shoes AND person_detected AND shoes_missing
FOR >= 5 seconds
THEN create violation + store snapshot + generate alert
```

---

**FR-PPE-005: Face Mask Detection**

System shall detect presence or absence of face mask.

Applicable zones: Paint Shop, Chemical Storage.

Rule:
```
IF zone.requires_mask AND person_detected AND mask_missing
FOR >= 3 seconds
THEN create violation + store snapshot + generate alert
```

---

### 8.2 Detection Pipeline

```
RTSP Frame
    ↓
Frame Sampling (configurable FPS)
    ↓
Person Detection (YOLO)
    ↓
Confidence Threshold Check
    ↓
ByteTrack — assign Track IDs
    ↓
For each tracked person:
    Helmet Check → if zone.requires_helmet
    Vest Check   → if zone.requires_vest
    Gloves Check → if zone.requires_gloves
    Shoes Check  → if zone.requires_shoes
    Mask Check   → if zone.requires_mask
    ↓
Rules Engine — evaluate duration + cooldown
    ↓
Violation Created (if rule fires)
    ↓
Snapshot Captured → MinIO
    ↓
Event Published → RabbitMQ
```

### 8.3 Violation Record

Each violation stores:
- Violation ID (UUID)
- Zone ID
- Camera ID
- Violation Type (Enum)
- Confidence Score
- ByteTrack Track ID
- Snapshot Key (MinIO object path)
- Timestamp
- Rules Engine Rule ID that fired

---

## Module 9 — Alert Management

### 9.1 Alert Categories & Severity

| Category | Alert Type | Severity | Auto-Assign To |
|---|---|---|---|
| PPE | Helmet Missing | High | Zone Supervisor |
| PPE | Vest Missing | Medium | Zone Supervisor |
| PPE | Gloves Missing | Medium | Zone Supervisor |
| PPE | Shoes Missing | Medium | Zone Supervisor |
| PPE | Mask Missing | Medium | Zone Supervisor |
| Occupancy | Overcrowding | High | Zone Supervisor |
| Access | Unauthorized Entry | High | Security + Supervisor |
| Infrastructure | Camera Offline | High | IT Admin |
| Infrastructure | Camera Degraded (low FPS) | Low | IT Admin |
| Infrastructure | Worker Offline | High | IT Admin |
| Safety | Multiple Violations Same Person | Critical | Safety Officer |

### 9.2 Alert Lifecycle

```
[OPEN]
  ↓ Supervisor acknowledges
[ACKNOWLEDGED]
  ↓ Supervisor starts action
[IN PROGRESS]
  ↓ Supervisor confirms corrective action taken
[CLOSED]
```

Every status transition is recorded in `alerts.alert_history` with:
- From Status
- To Status
- Changed By (user)
- Changed At (timestamp)
- Comment (mandatory on Close)

### 9.3 Alert Fields

- Alert ID (UUID)
- Alert Number (human-readable: ALT-2026-0001)
- Violation ID (FK, nullable for infra alerts)
- Factory ID
- Zone ID
- Camera ID
- Alert Type
- Severity (Critical / High / Medium / Low)
- Status (Open / Acknowledged / InProgress / Closed)
- Assigned To (user)
- Snapshot URL (pre-signed MinIO URL)
- Created On
- Acknowledged On
- Resolved On
- SLA Due At (based on severity SLA config)

### 9.4 Alert SLA

Configurable per severity:

| Severity | Acknowledgement SLA | Resolution SLA |
|---|---|---|
| Critical | 2 minutes | 15 minutes |
| High | 5 minutes | 30 minutes |
| Medium | 15 minutes | 2 hours |
| Low | 1 hour | 8 hours |

SLA breach shall trigger escalation notification to Safety Officer and Admin.

### 9.5 Alert Deduplication

System shall not create a new alert for the same violation type on the same camera if:
- An Open or Acknowledged alert of the same type already exists for that zone
- AND the cooldown period has not elapsed

Configurable cooldown period per violation type per zone.

### 9.6 Alert Filters

Alert list page shall support filtering by:
- Date range
- Factory
- Zone
- Camera
- Severity
- Status
- Violation type
- Assigned to
- SLA status (within SLA / breached)

---

## Module 10 — Incident Management

### 10.1 Incident vs Alert

Every alert of severity High or Critical automatically becomes an Incident.

| Field | Value |
|---|---|
| Incident Number | INC-2026-0001 (auto-generated) |
| Linked Alert | Alert ID |
| Incident Type | Derived from alert type |
| Zone | From alert |
| Camera | From alert |
| Timestamp | From alert |
| Severity | From alert |
| Status | Open / Under Investigation / Corrective Action / Closed |
| Assigned To | Safety Officer |
| Evidence | Snapshot + video clip reference (future) |
| Root Cause | Text (filled by Safety Officer) |
| Corrective Action | Text (mandatory on close) |
| Closed By | User |
| Closed At | Timestamp |

### 10.2 Incident Workflow

```
High/Critical Alert Created
    ↓
Incident Auto-Created (linked to alert)
    ↓
Safety Officer assigned
    ↓
Safety Officer reviews snapshot + occupancy data
    ↓
Safety Officer fills root cause + corrective action
    ↓
Incident Closed
    ↓
Alert auto-resolved (if still open)
    ↓
Audit entry created
```

---

## Module 11 — Dashboard

### 11.1 Executive Dashboard (Admin / Plant Manager / Viewer)

**Real-time metrics (WebSocket):**
- Total Cameras / Online / Offline
- Active Alerts by severity (Critical / High / Medium / Low)
- Open Incidents
- PPE Compliance % (today)
- Overall Safety Score
- Violations today (count + trend vs yesterday)

**Charts:**
- Violations by type (donut chart — today)
- Alert volume trend (last 7 days — bar chart)
- PPE compliance trend (last 30 days — line chart)
- Zone compliance heatmap (grid: zone × PPE type)

---

### 11.2 Safety Dashboard (Safety Officer)

- Violations by zone (today)
- Open alerts with SLA countdown
- Alert resolution time trend
- Top 5 repeat violation zones
- Shift-wise violation breakdown (if shift config enabled)
- Weekly violation trend

---

### 11.3 Zone Dashboard (Supervisor)

- Assigned zone occupancy gauge (real-time)
- Assigned zone cameras — live status
- Active alerts for assigned zones
- Recent violations (last 10)
- Zone safety score

---

### 11.4 Camera Dashboard

- Camera grid view (all cameras, status card per camera)
- Filter by: zone / status / worker
- Each card shows: camera name, zone, status, FPS, last seen
- Click → camera detail: full health info + recent violations

---

### 11.5 Worker Dashboard (Admin)

- AI worker list: status, assigned cameras, model version, heartbeat
- Worker health: frames processed per minute, inference latency (p50/p99)
- DLQ depth per worker
- Model version distribution

---

## Module 12 — Analytics

### 12.1 PPE Analytics

- Helmet compliance % — daily / weekly / monthly trend
- Vest compliance % — daily / weekly / monthly trend
- Violations by type — bar chart
- Violations by zone — horizontal bar
- Violations by hour of day — heatmap (zone × hour)
- Top 10 violation zones (ranking)
- Violation trend (last 90 days)

### 12.2 Occupancy Analytics

- Average occupancy per zone — bar chart
- Peak occupancy per zone per day — calendar heatmap
- Overcrowding events per zone — trend
- Occupancy by hour (heatmap: zone × hour)
- Zone utilization % (avg occupancy / max occupancy)

### 12.3 Alert Analytics

- Alert volume by day (last 30 days)
- Alert volume by severity
- Average acknowledgement time by role
- Average resolution time by zone
- SLA breach rate
- Alert escalation rate
- Top 5 alert types

### 12.4 Safety Score

Calculated weekly per factory and per zone.

```
Safety Score = (0.6 × PPE Compliance%) +
               (0.3 × (1 − normalized_incident_rate)) +
               (0.1 × alert_closure_speed_score)

Where:
  normalized_incident_rate = incidents / (person_hours / 1000)
  alert_closure_speed_score = 1 − (avg_closure_time / SLA_target_time)
```

Score displayed as:
- 90–100: Excellent (Green)
- 70–89: Good (Yellow)
- 50–69: Needs Improvement (Orange)
- < 50: Critical (Red)

---

## Module 13 — Reports

### 13.1 Report Types

| Report | Audience | Format | Frequency |
|---|---|---|---|
| Daily Safety Summary | Admin / Safety Officer | PDF | Daily (auto) |
| Weekly Compliance Report | Admin / Plant Manager | PDF + Excel | Weekly (auto) |
| Monthly Safety Scorecard | Management | PDF | Monthly (auto) |
| Alert Detail Report | Safety Officer | PDF + Excel | On-demand |
| Violation Evidence Report | Safety Officer / Auditor | PDF | On-demand |
| Camera Health Report | IT Admin | Excel | On-demand |
| Audit Trail Export | Admin | PDF + Excel | On-demand |
| Occupancy Trend Report | Plant Manager | Excel | On-demand |

### 13.2 Report Fields (Daily Safety Summary)

- Report period
- Factory name
- Total violations (by type)
- PPE compliance %
- Active alerts at end of day
- Alerts resolved today
- Camera uptime %
- Safety score
- Top 3 violation zones
- Escalated incidents

### 13.3 Scheduled Reports

- Admin configures report schedule (daily / weekly / monthly)
- System generates and emails PDF to configured recipients
- Reports stored in MinIO and accessible from Reports page

---

## Module 14 — Configuration (Rules Engine)

### 14.1 Zone Detection Config

Per-zone configurable settings (stored in `config.zone_configs`):

| Setting | Type | Default |
|---|---|---|
| person_threshold | DECIMAL | 0.70 |
| helmet_threshold | DECIMAL | 0.75 |
| vest_threshold | DECIMAL | 0.75 |
| gloves_threshold | DECIMAL | 0.70 |
| shoes_threshold | DECIMAL | 0.70 |
| mask_threshold | DECIMAL | 0.75 |
| max_occupancy | INT | From zone |
| frame_sample_fps | INT | 2 |
| ppe_required | JSONB | ["helmet","vest"] |
| restricted_zone | BOOLEAN | false |

### 14.2 Rules Engine Configuration

Each rule is stored in `config.zone_rules` and is fully configurable:

| Field | Type | Description |
|---|---|---|
| rule_id | UUID | |
| zone_id | UUID | |
| rule_name | VARCHAR | Human-readable name |
| condition_type | ENUM | HELMET_MISSING, VEST_MISSING, etc. |
| duration_seconds | INT | Sustained violation before alert fires |
| cooldown_seconds | INT | Min time between same alerts |
| severity | ENUM | |
| enabled | BOOLEAN | |
| actions | JSONB | ["CREATE_ALERT","STORE_SNAPSHOT","NOTIFY"] |
| notify_roles | JSONB | ["Supervisor","SafetyOfficer"] |
| notify_channels | JSONB | ["Email","InApp","WebPush"] |

### 14.3 Alert Routing Configuration

Admin configures who receives alerts per violation type per zone:
- Primary assignee (default: zone supervisor)
- Escalation assignee (default: safety officer)
- Escalation after: configurable SLA per severity

### 14.4 Notification Templates

Templates stored in DB, configurable per organization:
- Template name
- Channel (Email / Slack / Teams / Webhook)
- Subject template (with placeholders)
- Body template (with placeholders)
- Available placeholders: `{zone_name}`, `{camera_name}`, `{violation_type}`, `{timestamp}`, `{alert_url}`, `{snapshot_url}`

---

## Module 15 — Notifications

### 15.1 Notification Channels

| Channel | Use Case | Configuration |
|---|---|---|
| Email | Alert notifications + reports | SMTP server config |
| In-App | Real-time alert feed | Built-in (WebSocket) |
| Web Push | Browser push notifications | Web Push API keys |
| Slack | Team channel alerts | Slack Webhook URL |
| Microsoft Teams | Enterprise team alerts | Teams Webhook URL |
| Webhook | Custom integrations | HTTP POST URL + auth |

### 15.2 User Notification Preferences

Each user configures preferred channels per alert severity:

| Severity | User Choice |
|---|---|
| Critical | Email + In-App + Web Push |
| High | Email + In-App |
| Medium | In-App |
| Low | In-App |

### 15.3 Notification Delivery

- All notifications logged to `notifications.notification_log`
- Failed delivery: retry 3 times with exponential backoff
- All retries failed: escalate to admin + log to audit
- Delivery status tracked: Sent / Delivered / Failed

---

## Module 16 — Audit Trail

### 16.1 Audited Actions

Every sensitive action is recorded:

| Action | Trigger |
|---|---|
| UserCreated | New user account |
| UserUpdated | Profile or role changed |
| UserDisabled | Account deactivated |
| LoginSuccess | Successful login |
| LoginFailed | Failed login attempt |
| Logout | Session terminated |
| AlertAcknowledged | Supervisor acknowledges |
| AlertResolved | Alert closed |
| AlertReassigned | Alert reassigned to different user |
| IncidentClosed | Incident closed with root cause |
| ConfigChanged | Zone config or rule changed |
| CameraAdded | New camera registered |
| CameraRemoved | Camera deleted |
| ModelUpdated | AI model version changed |
| UnauthorizedAccess | 403 response on any endpoint |
| ReportGenerated | Report created |
| UserPasswordReset | Password reset performed |

### 16.2 Audit Log Fields

- ID (UUID)
- User ID
- Action (from above list)
- Entity Type (User / Alert / Camera / Config / ...)
- Entity ID
- Old Value (JSONB — before state)
- New Value (JSONB — after state)
- IP Address
- User Agent
- Correlation ID (request ID)
- Timestamp

### 16.3 Audit Log Rules

- Append-only: no UPDATE or DELETE permitted at database level
- Accessible only by Admin role
- Exportable to PDF or Excel for compliance
- Retained for 36 months online, 5 years cold archive

---

## Module 17 — Health & System Status

### 17.1 Health Endpoints

| Endpoint | Purpose |
|---|---|
| GET /health/live | Liveness check — is process running? |
| GET /health/ready | Readiness check — can it serve traffic? |
| GET /health/status | Full system status (DB, Redis, RabbitMQ, MinIO) |

### 17.2 Readiness Checks

System is ready only when:
- PostgreSQL: connected and responding
- Redis: connected and responding
- RabbitMQ: connected and queue accessible
- MinIO: connected and bucket accessible

### 17.3 System Status Response

```json
{
  "status": "healthy",
  "timestamp": "2026-01-01T10:00:00Z",
  "components": {
    "database":  { "status": "up",   "latency_ms": 2 },
    "redis":     { "status": "up",   "latency_ms": 1 },
    "rabbitmq":  { "status": "up",   "queue_depth": 0 },
    "minio":     { "status": "up",   "latency_ms": 5 },
    "ai_workers": {
      "total": 4,
      "online": 4,
      "offline": 0
    }
  }
}
```

---

# 10. Business Rules

| Rule ID | Rule | Notes |
|---|---|---|
| BR-001 | Camera must be assigned to a zone before activation | Enforced at API level |
| BR-002 | Zone max occupancy cannot be 0 | Min value: 1 |
| BR-003 | Alert deduplication: same violation type + same zone → no new alert during cooldown | Cooldown configurable |
| BR-004 | Alert SLA breach → auto-escalation to Safety Officer | Configurable per severity |
| BR-005 | Audit log is immutable — no update or delete | DB-level enforcement |
| BR-006 | Supervisor can only access alerts for their assigned zones | RBAC enforcement |
| BR-007 | Violation snapshot must be stored before alert is created | Atomicity required |
| BR-008 | Config version must increment on every zone config save | For race-condition-safe worker sync |
| BR-009 | AI workers must not access the database directly | Architecture constraint |
| BR-010 | Refresh token reuse after revocation → full session invalidation | Security rule |
| BR-011 | Account locked after 5 failed logins for 15 minutes | Security rule |
| BR-012 | Password must meet complexity policy | Security rule |
| BR-013 | Incident closure requires root cause + corrective action text | Mandatory fields |
| BR-014 | Report download links expire after 24 hours | Security rule |
| BR-015 | MinIO snapshot pre-signed URLs expire in 15 minutes | Security rule |

---

# 11. Non-Functional Requirements

## Performance

| Requirement | Target |
|---|---|
| Alert latency (detection → notification) | ≤ 5 seconds |
| API response time (p95) | ≤ 200ms |
| Dashboard load time (initial) | ≤ 2 seconds |
| WebSocket push latency | ≤ 1 second |
| Report generation time | ≤ 10 seconds |
| Camera offline detection | ≤ 60 seconds |
| Config update propagation to workers | ≤ 10 seconds |
| Inference latency per frame (GPU) | ≤ 50ms |
| Inference latency per frame (CPU) | ≤ 500ms |

## Capacity

| Requirement | Initial | Future |
|---|---|---|
| Cameras | 50 | 1000+ |
| Factories | 1 | 100+ |
| Concurrent users | 50 | 500+ |
| Concurrent WebSocket connections | 100 | 1000+ |
| Events per second (RabbitMQ) | 50 | 5000+ |
| Violations stored per day | 10,000 | 1,000,000 |

## Availability

| Requirement | Target |
|---|---|
| System availability | 99.5% |
| Planned downtime window | Saturday 2–4 AM |
| Recovery Time Objective (RTO) | 30 minutes |
| Recovery Point Objective (RPO) | 5 minutes |

## Reliability

- Zero data loss on AI worker crash (Dead Letter Queue)
- Zero event loss on backend restart (RabbitMQ durable queues)
- Automatic camera stream reconnection
- Circuit breaker per camera

## Scalability

- Horizontal scaling: add AI workers, add backend instances — no code change
- Database: partition by month, read replicas at scale
- Cache: Redis cache reduces DB load by 80%+
- WebSocket: Redis Pub/Sub for cross-instance broadcast

---

# 12. AI & Detection Requirements

| Requirement | Target |
|---|---|
| Helmet detection accuracy | ≥ 90% |
| Vest detection accuracy | ≥ 88% |
| Person detection accuracy | ≥ 95% |
| Occupancy count accuracy | ≥ 95% |
| False positive rate | ≤ 5% |
| False negative rate | ≤ 10% |

## Model Requirements

- Model format: ONNX (for runtime flexibility) + PyTorch (for training)
- CUDA support: NVIDIA GPU acceleration
- CPU fallback: automatic when no GPU detected
- Model versioning: stored in MinIO, versioned by date + hash
- Hot-swap: model update without stream restart

## Frame Processing Requirements

- Default sampling: 2 FPS from 25 FPS stream (configurable per zone)
- Maximum detection lag: 500ms from frame capture to event publish
- Snapshot resolution: minimum 640×480, saved as JPEG (quality 85)

---

# 13. Security Requirements

| Category | Requirement |
|---|---|
| Authentication | JWT Access Token (8h) + Refresh Token Rotation (7d) |
| Token Security | Blacklisting on logout, replay attack prevention |
| Authorization | RBAC enforced on every endpoint |
| Transport | HTTPS enforced in production (TLS 1.2+) |
| Data Encryption | RTSP URLs encrypted at rest (AES-256) |
| Input Validation | Pydantic v2 strict validation on all inputs |
| SQL Injection | SQLAlchemy ORM — no raw SQL |
| XSS | React escaping + CSP headers |
| CSRF | SameSite=Strict cookies + token header for API |
| Rate Limiting | Per user per role (Redis sliding window) |
| File Upload | JPEG/PNG only, max 5MB, MIME type validation |
| Audit | All sensitive actions logged immutably |
| Secrets | Environment variables only, never committed |
| OWASP | Top 10 mitigations implemented |
| Account Lockout | 5 failed attempts → 15 min lockout |
| Password Policy | Min 8 chars, uppercase, number, special char |

---

# 14. Reporting Requirements

| Requirement | Detail |
|---|---|
| PDF generation | Server-side using WeasyPrint / ReportLab |
| Excel generation | openpyxl |
| Max report size | 50MB |
| Report storage | MinIO (auto-deleted after 30 days) |
| Download link expiry | 24 hours |
| Scheduled reports | Configurable: daily / weekly / monthly |
| Email delivery | PDF attached to scheduled report email |
| Charts in PDF | Server-rendered charts (matplotlib / plotly) |

---

# 15. Notification Requirements

| Channel | Library | SLA |
|---|---|---|
| Email | SMTP / SendGrid | ≤ 30 seconds |
| In-App | WebSocket | ≤ 1 second |
| Web Push | Web Push API | ≤ 5 seconds |
| Slack | Slack Webhook | ≤ 10 seconds |
| Teams | Teams Webhook | ≤ 10 seconds |
| Webhook | HTTP POST | ≤ 10 seconds |

Retry policy: 3 attempts with 30s / 2min / 10min backoff.

All notifications logged with delivery status.

---

# 16. Integration Requirements

| System | Type | Priority | Notes |
|---|---|---|---|
| Email / SMTP | Native | Phase 1 | Required for notifications |
| Slack | Webhook | Phase 1 | Alert channel |
| Microsoft Teams | Webhook | Phase 1 | Enterprise teams |
| SMS Gateway | API | Phase 2 | Twilio / local provider |
| SAP | REST API | Phase 3 | Work order creation |
| HRMS | REST API | Phase 2 | Worker identity linkage |
| Attendance System | REST API | Phase 2 | Auto badge → person link |
| Access Control | REST API | Phase 3 | Badge vs camera cross-ref |
| Fire Alarm System | REST API | Phase 3 | Correlated alerts |

---

# 17. Hardware Requirements

## Development Environment

| Component | Specification |
|---|---|
| CPU | Intel Core Ultra 7 165H (or equivalent 8+ core) |
| RAM | 32–64 GB |
| GPU | NVIDIA RTX 2000 Ada (or equivalent) |
| Storage | 512 GB SSD |
| OS | Windows 11 + WSL2 / Ubuntu 22.04 |

## Production — 50 Cameras (Initial)

| Server | Role | Spec |
|---|---|---|
| Server 1 | App + DB + Cache + Queue | 24-core CPU, 64 GB RAM, 2 TB SSD |
| Server 2 | GPU Worker 1 (25 cameras) | 8-core CPU, 32 GB RAM, RTX 4090, 1 TB SSD |
| Server 3 | GPU Worker 2 (25 cameras) | 8-core CPU, 32 GB RAM, RTX 4090, 1 TB SSD |

## Production — 200 Cameras

| Server | Role | Count |
|---|---|---|
| App Servers | FastAPI backend (load balanced) | 2 |
| DB Server | PostgreSQL primary + replica | 2 |
| Cache/Queue | Redis + RabbitMQ | 1 |
| Storage | MinIO | 1 |
| GPU Workers | 25 cameras each | 8 |
| Monitoring | Prometheus + Grafana + Loki | 1 |

---

# 18. Workflow Scenarios

## Scenario 1 — Helmet Missing Detection

```
Worker enters Welding Area without helmet.
Camera detects person via YOLO.
ByteTrack assigns Track ID = T-042.
PPE validator: helmet_detected = False.
Rules engine: helmet_missing FOR 3 seconds → rule fires.
Snapshot captured → uploaded to MinIO.
Event published: HelmetMissingDetected (zone=ZONE-WELDING, camera=CAM-003).
Backend consumer receives event.
Violation record created.
Alert created: ALT-2026-0087, Severity=High, Status=Open.
Incident created: INC-2026-0031 (linked to alert).
Redis cache invalidated.
WebSocket broadcast → supervisor dashboard updated.
Notification dispatched:
  → In-App: Supervisor sees alert card appear in real time.
  → Email: Supervisor receives email with snapshot.
  → Slack: #safety-welding channel notified.
Audit entry created: AlertCreated.
```

---

## Scenario 2 — Zone Overcrowding

```
Welding Area max occupancy = 5.
Workers entering gradually.
Current count reaches 6.
OccupancyUpdated event: count=6, max=5.
Rules engine: overcrowding = True → rule fires (immediate, no duration).
Event published: OvercrowdingDetected.
Alert created: ALT-2026-0088, Severity=High.
Supervisor + Safety Officer notified.
Dashboard occupancy gauge turns Red.
Count drops to 4 → occupancy gauge returns to Green.
Alert remains Open until supervisor closes it.
```

---

## Scenario 3 — Camera Offline

```
Camera CAM-005 loses RTSP connection.
Worker retries: 5s → 15s → 60s.
All retries fail.
Event published: CameraOfflineDetected (camera=CAM-005).
Alert created: ALT-2026-0089, Severity=High.
IT Admin notified via Email + In-App.
Dashboard: CAM-005 card turns Red with "Offline" badge.
Camera reconnects 10 minutes later.
Event published: CameraReconnected.
Alert auto-closed.
Dashboard: CAM-005 card returns to Green.
```

---

## Scenario 4 — SLA Breach Escalation

```
Alert ALT-2026-0090 (Severity=High) created at 10:00 AM.
SLA: acknowledgement within 5 minutes.
10:05 AM: Alert still Open — no acknowledgement.
Escalation triggered.
Safety Officer receives escalation notification.
Audit entry: AlertEscalated.
10:07 AM: Safety Officer acknowledges → status = Acknowledged.
10:35 AM: SLA resolution time (30 min) approaching.
10:30 AM: Resolved by supervisor → status = Closed.
Alert closure time: 30 minutes (within SLA).
```

---

## Scenario 5 — Zone Config Change (Hot-Swap)

```
Admin increases helmet threshold: 0.75 → 0.80 for Welding Area.
PUT /api/v1/config/zone/ZONE-WELDING
config.zone_configs updated: version 7 → 8.
ConfigUpdated event published: zone_id=ZONE-WELDING, version=8.
Worker 1 receives event.
Worker 1 local_version=7 < event.version=8 → apply new config.
Worker 1 updates in-memory threshold: helmet_threshold = 0.80.
Worker 1 continues stream — no restart.
Change takes effect within 5 seconds.
Config change logged to audit.
```

---

# 19. Success Criteria

| Criterion | Target | Measurement |
|---|---|---|
| Helmet detection accuracy | ≥ 90% | Test dataset evaluation |
| Occupancy count accuracy | ≥ 95% | Benchmark test |
| Alert latency | ≤ 5 seconds | End-to-end timing test |
| Camera offline detection | ≤ 60 seconds | Disconnect test |
| Config propagation to workers | ≤ 10 seconds | Timing test |
| API response time (p95) | ≤ 200ms | Load test |
| System availability | ≥ 99.5% | 30-day uptime measurement |
| Camera support (initial) | 50 cameras | Capacity test |
| Camera support (future) | 200+ cameras | Architecture review |
| Zero data loss on worker crash | 0 lost events | DLQ recovery test |
| Audit trail completeness | 100% | Manual audit check |
| SLA breach escalation | 100% automated | Test per severity |
| Report generation | ≤ 10 seconds | Timing test |
| WebSocket latency | ≤ 1 second | Measured push delay |

---

# 20. Future Roadmap

## Phase 2 (3–6 months post-launch)

- Face recognition — link detected persons to worker identities
- Visitor management — track non-employees
- Attendance integration — auto-correlate camera detection with HRMS
- Gloves + shoes detection improvement
- SMS notification channel
- Mobile PWA (Progressive Web App) for supervisors
- Shift management — shift-wise violation analysis

## Phase 3 (6–12 months)

- Fire and smoke detection (YOLO model extension)
- Fall detection
- SAP work order integration on violation
- Access control cross-reference (badge vs camera)
- Fire alarm system correlation
- Multi-language UI (Hindi, regional languages)
- Offline mode for dashboard (PWA cache)

## Phase 4 (12–18 months)

- Forklift and vehicle detection
- Unsafe behavior detection (e.g., running in restricted areas)
- AI Risk Scoring — predict high-risk periods before incidents occur
- Digital safety audits — structured audit workflow in platform
- Predictive analytics — forecast violation trends
- Edge AI — on-camera inference for low-bandwidth factories
- Kubernetes deployment for 1000+ camera scale
- Multi-region deployment

---

*End of Document — VisionGuard AI BRD v2.0 Enterprise Edition*
