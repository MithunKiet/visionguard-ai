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
Organization: {Enterprise Name}

├── Factory: {Factory Name 1}
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
└── Factory: {Factory Name 2}
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

---

# 21. Enterprise Hierarchy & Multi-Factory Architecture

## 21.1 Overview

VisionGuard AI is not a single-factory monitoring tool. It is an **Enterprise Platform** designed to centrally manage multiple factories under one organization (Enterprise), while keeping each factory's data, users, and configurations completely isolated.

**Real-world example:**

```
Enterprise: {Enterprise Name}
    ├── AC Factory          ({City A})
    ├── Washing Machine Factory  ({City B})
    ├── Refrigerator Factory     ({City C})
    └── E-commerce Factory       ({City D})
```

All four factories are managed from a single VisionGuard AI deployment. The Head Office (HO) System Administrator can monitor all factories centrally. Each Factory Admin sees only their own factory.

---

## 21.2 5-Level Hierarchy

```
Level 1 → Enterprise        {Enterprise Name}
Level 2 → Factory           AC Factory
Level 3 → Department        Assembly Department
Level 4 → Zone              Zone A (Main Assembly Line)
Level 5 → Camera            CAM-001, CAM-002
```

### Why Department Level

The original BRD had only Factory → Zone. Department is a required addition because:

- Large factories have 10–20 zones — grouping under departments is essential
- Department Head needs isolated visibility (only their department)
- Alert routing must reach Department Head, not just Zone Supervisor
- Analytics must aggregate at department level
- Different departments have different PPE requirements (Welding ≠ Packaging)

---

## 21.3 Enterprise Structure Example

```
Enterprise: {Enterprise Name}
│
├── Factory: AC Factory ({City A})
│     ├── Department: Assembly
│     │     ├── Zone: Main Assembly Line     (Max: 10) [3 cameras]
│     │     ├── Zone: Sub-Assembly Area      (Max: 8)  [2 cameras]
│     │     └── Zone: Component Store        (Max: 5)  [1 camera]
│     ├── Department: Welding
│     │     ├── Zone: Welding Bay A          (Max: 5)  [2 cameras]
│     │     └── Zone: Welding Bay B          (Max: 5)  [2 cameras]
│     ├── Department: Quality Control
│     │     └── Zone: QC Lab                (Max: 6)  [2 cameras]
│     └── Department: Packaging
│           └── Zone: Packing Line           (Max: 8)  [2 cameras]
│
├── Factory: Washing Machine Factory ({City B})
│     ├── Department: Drum Assembly
│     └── Department: Final Assembly
│
├── Factory: Refrigerator Factory ({City C})
│     └── ...
│
└── Factory: E-commerce Factory ({City D})
      └── ...
```

---

## 21.4 User Roles — Updated for Enterprise

### Role 1 — HO System Administrator (Head Office Admin)

**Scope:** Entire Enterprise — all factories.

**Responsibilities:**
- View enterprise-wide dashboard (all factories at a glance)
- Cross-factory analytics and comparison
- Manage all factories, departments, zones, cameras
- Manage all users across all factories
- View all alerts across all factories
- Generate enterprise-level compliance reports
- Access full audit trail across all factories
- Manage AI worker assignments
- Configure enterprise-wide settings

**Key Differentiator:** Only role that sees cross-factory data.

---

### Role 2 — Factory Admin

**Scope:** Single assigned factory only.

**Responsibilities:**
- Manage departments, zones, cameras within their factory
- Manage users within their factory
- View factory-level dashboard, alerts, analytics
- Generate factory-level reports
- Configure factory-level detection rules

**Restriction:** Cannot see any data from other factories — even if they belong to the same enterprise.

---

### Role 3 — Department Head

**Scope:** Single assigned department within a factory.

**Responsibilities:**
- Monitor all zones within their department
- View department-level dashboard and analytics
- Acknowledge and resolve alerts in their department
- View department compliance reports

**Restriction:** Cannot see zones or alerts outside their department.

---

### Role 4 — Safety Officer

**Scope:** Single factory.

**Responsibilities:**
- Review and investigate all alerts in their factory
- Generate safety compliance reports
- View factory-wide analytics

---

### Role 5 — Supervisor

**Scope:** Assigned zones only (within a department).

**Responsibilities:**
- Monitor assigned zones in real time
- Acknowledge and resolve alerts for assigned zones
- Take corrective actions

---

### Role 6 — Viewer

**Scope:** Assigned dashboard scope (read-only).

---

## 21.5 Access Control Matrix

| Feature | HO Admin | Factory Admin | Dept Head | Safety Officer | Supervisor | Viewer |
|---|---|---|---|---|---|---|
| Enterprise Dashboard | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| All Factories View | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Own Factory Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Other Factory Data | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dept Dashboard | ✅ | ✅ | ✅ (own) | ✅ | ❌ | ❌ |
| Zone Dashboard | ✅ | ✅ | ✅ (own dept) | ✅ | ✅ (assigned) | ✅ (assigned) |
| User Management | ✅ (all) | ✅ (own factory) | ❌ | ❌ | ❌ | ❌ |
| Alert Management | ✅ | ✅ | ✅ (own dept) | ✅ | ✅ (own zones) | ❌ |
| Config Management | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Enterprise Reports | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Factory Reports | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Audit Log | ✅ (all) | ✅ (own factory) | ❌ | ✅ (own actions) | ❌ | ❌ |

---

## 21.6 Enterprise Dashboard — HO Admin View

The Enterprise Dashboard is exclusive to HO Admin. It provides a bird's-eye view of all factories simultaneously.

### Dashboard Panels

**Factory Comparison Panel:**

| Factory | Safety Score | Active Alerts | Cameras Online | PPE Compliance | Violations Today |
|---|---|---|---|---|---|
| AC Factory | 94% | 2 | 18/18 | 96.2% | 3 |
| WM Factory | 87% | 7 | 22/24 | 89.1% | 14 |
| Fridge Factory | 91% | 1 | 12/12 | 93.5% | 5 |
| E-comm Factory | 96% | 0 | 8/8 | 98.1% | 1 |

**Enterprise Totals:**
- Overall Safety Score: 92%
- Total Active Alerts: 10
- Total Cameras: 60 (58 online, 2 offline)
- Enterprise PPE Compliance: 94.2%

**Charts (Enterprise Level):**
- Safety score trend per factory (last 30 days — line chart, one line per factory)
- Violations by factory (bar chart — today)
- Worst performing zones across all factories (top 10 ranking)
- Alert volume heatmap (factory × day of week)

**Drill-down:** HO Admin can click any factory card to enter that factory's dashboard.

---

## 21.7 Factory Isolation Rules

**FR-ENT-001:** A Factory Admin shall only see data belonging to their assigned factory.

**FR-ENT-002:** System shall enforce factory isolation at the database query level — not just at the UI level.

**FR-ENT-003:** API shall return HTTP 403 if a Factory Admin attempts to access another factory's data — even within the same enterprise.

**FR-ENT-004:** All alert notifications shall only be sent to users within the correct factory scope.

**FR-ENT-005:** Reports generated by a Factory Admin shall only contain data from their factory.

**FR-ENT-006:** Audit log entries shall be visible to Factory Admin only for their own factory's actions.

---

## 21.8 Cross-Factory Analytics (HO Admin Only)

HO Admin has access to analytics that span all factories:

**Cross-Factory PPE Comparison:**
- Helmet compliance % per factory — bar chart
- Vest compliance % per factory — bar chart
- Which factory has the worst PPE compliance this month?

**Cross-Factory Alert Analysis:**
- Alert volume per factory per week
- Average alert resolution time per factory
- Which factory has the most SLA breaches?

**Safety Score Ranking:**
- Factory ranking by safety score (best to worst)
- Month-over-month improvement per factory
- Which department across all factories has the most violations?

**Enterprise KPI Summary (Monthly Report):**
- Total violations across all factories
- Total incidents
- Enterprise-wide PPE compliance %
- Enterprise safety score
- Factory-wise breakdown

---

## 21.9 Multi-Enterprise Support

VisionGuard AI is designed to be supplied to multiple enterprise clients. Each enterprise client gets complete data isolation:

```
Enterprise 1: {Enterprise Name}
    → enterprise_id: uuid-enterprise-1
    → 4 factories, 60 cameras

Enterprise 2: {Enterprise Name 2}
    → enterprise_id: uuid-enterprise-2
    → 6 factories, 350 cameras

Enterprise 3: {Enterprise Name 3}
    → enterprise_id: uuid-enterprise-3
    → 3 factories, 150 cameras
```

**Isolation guarantee:**
- {Enterprise Name}'s HO Admin cannot access Tata's data
- Enforced via PostgreSQL Row Level Security (RLS)
- Every table carries `enterprise_id` — every query is scoped to it

### Super Admin (VisionGuard Internal Team)

A `SUPER_ADMIN` role exists for the VisionGuard platform operations team:

**Capabilities:**
- Create and manage enterprise accounts
- Activate / suspend enterprise access
- View platform health across all enterprises
- Access any enterprise for support purposes (audit-logged)
- Manage platform-wide configurations

**Security:**
- Accessed via separate `/superadmin/` URL
- Requires MFA
- Every Super Admin action is logged in a separate immutable platform audit log
- Super Admin actions are never visible in client-facing audit logs

---

## 21.10 New Functional Requirements

### FR-ENT-001 to FR-ENT-010 — Enterprise Management

**FR-ENT-001:** System shall support multiple enterprises on a single platform deployment.

**FR-ENT-002:** Each enterprise shall have complete data isolation from all other enterprises.

**FR-ENT-003:** HO Admin shall see all factories within their enterprise from a single dashboard.

**FR-ENT-004:** Factory Admin shall only see their own factory's data — no cross-factory visibility.

**FR-ENT-005:** System shall enforce access scope at the API middleware level on every request.

**FR-ENT-006:** Alert notifications shall be scoped to the correct factory — a Factory Admin from AC Factory shall not receive alerts from WM Factory.

**FR-ENT-007:** Reports shall be scoped to the requesting user's access level automatically.

**FR-ENT-008:** Audit log shall be scoped per factory for Factory Admin, and enterprise-wide for HO Admin.

**FR-ENT-009:** Super Admin shall be able to create, activate, and suspend enterprise accounts.

**FR-ENT-010:** Super Admin access to any enterprise shall be logged in a separate immutable platform audit log.

### FR-DEPT-001 to FR-DEPT-005 — Department Management

**FR-DEPT-001:** Admin shall create departments within a factory with:
- Department Name
- Department Code (unique within factory)
- Department Head (linked user)
- Description
- Status (Active / Inactive)

**FR-DEPT-002:** Department shall group multiple zones.

**FR-DEPT-003:** Department Head shall receive alerts for all zones within their department.

**FR-DEPT-004:** Department dashboard shall show:
- All zones in department with live occupancy
- Active alerts for department
- Department PPE compliance %
- Department safety score

**FR-DEPT-005:** Analytics shall be available at department level:
- Violations by zone within department
- Department compliance trend
- Department vs factory average comparison

---

## 21.11 Updated Database Tables

### enterprises (new)
```
id                UUID PK
name              VARCHAR          ({Enterprise Name})
code              VARCHAR UNIQUE   (HAIER-IN)
industry          VARCHAR
contact_person    VARCHAR
contact_email     VARCHAR
status            ENUM (Active, Inactive, Suspended)
created_on        TIMESTAMPTZ
created_by        UUID
```

### departments (new)
```
id                UUID PK
enterprise_id     FK → enterprises
factory_id        FK → factories
name              VARCHAR
code              VARCHAR (unique within factory)
head_user_id      FK → users
description       TEXT
status            ENUM
created_on        TIMESTAMPTZ
created_by        UUID
modified_by       UUID
version           INT DEFAULT 1
deleted_at        TIMESTAMPTZ
```

### factories (updated)
```
enterprise_id     FK → enterprises   ← ADDED
```

### zones (updated)
```
department_id     FK → departments   ← ADDED
```

### All other tables (updated)
```
enterprise_id     FK → enterprises   ← ADDED to every table
                                        for RLS enforcement
```

---

## 21.12 Updated Workflow Scenarios

### Scenario 6 — HO Admin Cross-Factory Monitoring

```
HO Admin logs in to VisionGuard AI.
Enterprise dashboard loads showing all 4 factories.
WM Factory shows: Safety Score 87%, Active Alerts 7, 2 cameras offline.
HO Admin notices WM Factory is underperforming vs others.
HO Admin clicks WM Factory → enters WM Factory dashboard.
Sees: 7 open alerts, Welding Dept has 5 of them.
HO Admin contacts WM Factory Admin via platform notification.
WM Factory Admin acknowledges and begins investigation.
HO Admin returns to enterprise dashboard — monitors resolution.
```

---

### Scenario 7 — Factory Admin Isolation

```
AC Factory Admin logs in.
Dashboard shows only AC Factory data.
AC Factory Admin tries to access:
  GET /api/v1/factories/uuid-factory-2/alerts
System returns: 403 Forbidden
Audit log entry created: UnauthorizedAccess
AC Factory Admin has no visibility into WM Factory.
```

---

### Scenario 8 — Department Head Alert Routing

```
Worker in Welding Bay A (AC Factory > Welding Dept > Zone A) missing helmet.
Alert created with full hierarchy:
  enterprise_id = uuid-enterprise-1
  factory_id    = uuid-factory-1
  department_id = uuid-welding-dept
  zone_id       = uuid-zone-a

Notifications sent:
  Zone Supervisor (Welding Bay A) → In-App + Email
  Department Head (Welding Dept)  → In-App + Email
  Factory Safety Officer          → In-App
  HO Admin                        → Visible on enterprise dashboard

AC Factory Admin → sees it on factory dashboard
WM Factory Admin → does NOT receive this alert (different factory)
```

---

*End of Enterprise Hierarchy & Multi-Factory Architecture Section*

---

# 22. Dynamic Branding Requirements

## 22.1 Core Rule

**No company name, logo, or brand asset shall be hardcoded anywhere in the VisionGuard AI platform.**

This applies to:
- All UI screens (dashboard, login, alerts, reports, settings)
- All email notifications
- All PDF and Excel reports
- All export filenames
- All audit log display text
- All notification templates

Every piece of branding must be loaded dynamically from the database at runtime, based on the logged-in user's enterprise.

## 22.2 Enterprise Branding Fields

| Field | Type | Purpose |
|---|---|---|
| `name` | VARCHAR | Shown in UI headers, emails, PDF reports |
| `code` | VARCHAR | Used in export filenames |
| `logo_url` | VARCHAR | MinIO path — served as pre-signed URL |
| `favicon_url` | VARCHAR | Browser tab icon |
| `primary_color` | VARCHAR | Hex color for UI theme |
| `secondary_color` | VARCHAR | Secondary brand color |
| `tagline` | VARCHAR | Optional subtitle on login page |

## 22.3 Functional Requirements

**FR-BRD-001:** System shall display enterprise name dynamically from database on all UI screens.

**FR-BRD-002:** System shall display enterprise logo dynamically from MinIO storage on login page, dashboard header, and all PDF reports.

**FR-BRD-003:** System shall apply enterprise primary color as UI theme color dynamically.

**FR-BRD-004:** All email notification subjects and bodies shall use enterprise name from database — no hardcoded company names.

**FR-BRD-005:** All generated PDF reports shall include enterprise name and logo from database in header and footer.

**FR-BRD-006:** All export filenames shall use enterprise code from database (e.g. `{enterprise_code}_report_2026.pdf`).

**FR-BRD-007:** Enterprise Admin shall be able to upload and update logo via platform settings.

**FR-BRD-008:** Super Admin shall be able to set branding for any enterprise on their behalf.

**FR-BRD-009:** Logo shall be stored in MinIO under `logos/{enterprise_id}/logo.png` and served via pre-signed URL.

**FR-BRD-010:** Browser tab favicon shall be set dynamically from `enterprise.favicon_url`.

## 22.4 Where Branding Appears

| Location | Dynamic Value |
|---|---|
| Browser tab | `{enterprise.name} — VisionGuard AI` |
| Login page logo | `enterprise.logo_url` |
| Login page heading | `enterprise.name` |
| Dashboard header | `enterprise.logo_url` + `enterprise.name` |
| UI accent color | `enterprise.primary_color` |
| Email subject | `[{enterprise.name}] Alert — {violation_type}` |
| Email header | `enterprise.logo_url` + `enterprise.name` |
| PDF report header | `enterprise.name` + `enterprise.logo_url` |
| PDF report footer | `enterprise.name` |
| Export filename | `{enterprise.code}_safety_report_2026.pdf` |

---

*End of Dynamic Branding Requirements Section*

---

# 23. First Time Setup & Onboarding Flow

## 23.1 Overview

When VisionGuard AI is deployed for a new enterprise client, the system must guide administrators through a structured onboarding process. No factory, department, zone, or camera data exists initially — the platform must be configured before monitoring can begin.

There are two onboarding actors:

| Actor | Role | Responsibility |
|---|---|---|
| Super Admin | VisionGuard internal team | Creates enterprise + first HO Admin user |
| HO Admin (Enterprise Admin) | Client's head office admin | Creates factories, departments, zones, cameras |

---

## 23.2 Complete Onboarding Flow

```
PHASE 1 — Super Admin Setup (VisionGuard Team)

Step 1 → Super Admin logs in
         (Platform default credentials, MFA required)
         ↓
Step 2 → Creates Enterprise account
         Fields: Enterprise Name, Code, Industry,
                 Logo, Primary Color, Contact Person,
                 Contact Email, Status
         ↓
Step 3 → Creates first HO Admin user for enterprise
         Fields: Full Name, Email, Temporary Password
         Role: HO_ADMIN
         ↓
Step 4 → System sends Welcome Email to HO Admin
         Contains: Login URL, Temporary Password,
                   Password reset link (expires 24h)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 2 — HO Admin First Login

Step 5 → HO Admin receives Welcome Email
         ↓
Step 6 → HO Admin clicks login link
         Prompted to set new password (mandatory)
         ↓
Step 7 → System detects: is_first_login = true
                          setup_completed = false
         Redirects to Setup Wizard automatically
         ↓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 3 — Setup Wizard (HO Admin completes)

Step 8  → Screen 1: Welcome Screen
Step 9  → Screen 2: Create First Factory
Step 10 → Screen 3: Create First Department
Step 11 → Screen 4: Create First Zone + PPE Config
Step 12 → Screen 5: Add First Camera (RTSP URL)
Step 13 → Screen 6: Summary + Launch Dashboard
          ↓
Step 14 → setup_completed = true saved to DB
          ↓
Step 15 → AI Worker auto-assigned to cameras
          ↓
Step 16 → Dashboard goes live ✅
```

---

## 23.3 Setup Wizard — Screen Details

### Screen 1 — Welcome

```
┌──────────────────────────────────────────┐
│                                          │
│   [Enterprise Logo]                      │
│                                          │
│   Welcome to VisionGuard AI              │
│   {enterprise.name}                      │
│                                          │
│   Let's set up your safety monitoring    │
│   platform in a few simple steps.        │
│                                          │
│   ● Create Factory                       │
│   ● Add Departments                      │
│   ● Configure Zones                      │
│   ● Connect Cameras                      │
│                                          │
│              [Get Started →]             │
│                                          │
└──────────────────────────────────────────┘
```

---

### Screen 2 — Create First Factory

```
┌──────────────────────────────────────────┐
│  Step 1 of 4 — Factory Details           │
│  ████░░░░░░░░░░ 25%                      │
│                                          │
│  Factory Name *    [________________]    │
│  Factory Code *    [________________]    │
│  Location          [________________]    │
│  Plant Head        [Select User ▼]       │
│  Description       [________________]    │
│                                          │
│  [← Back]              [Save & Next →]   │
└──────────────────────────────────────────┘
```

**Validation:**
- Factory Name: required, max 100 chars
- Factory Code: required, unique within enterprise, alphanumeric + hyphen only
- Plant Head: optional at this stage (can be assigned later)

---

### Screen 3 — Create First Department

```
┌──────────────────────────────────────────┐
│  Step 2 of 4 — Department Details        │
│  ████████░░░░░░ 50%                      │
│                                          │
│  Factory: {selected factory name}        │
│                                          │
│  Department Name * [________________]    │
│  Department Code * [________________]    │
│  Department Head   [Select User ▼]       │
│  Description       [________________]    │
│                                          │
│  + Add Another Department                │
│                                          │
│  [← Back]              [Save & Next →]   │
└──────────────────────────────────────────┘
```

---

### Screen 4 — Create First Zone + PPE Config

```
┌──────────────────────────────────────────┐
│  Step 3 of 4 — Zone Configuration        │
│  ████████████░░ 75%                      │
│                                          │
│  Department: {selected dept name}        │
│                                          │
│  Zone Name *       [________________]    │
│  Zone Code *       [________________]    │
│  Max Occupancy *   [____]                │
│  Supervisor        [Select User ▼]       │
│  Restricted Zone   [ ] Yes               │
│                                          │
│  PPE Requirements:                       │
│  [✓] Helmet   [✓] Safety Vest            │
│  [ ] Gloves   [ ] Safety Shoes           │
│  [ ] Face Mask                           │
│                                          │
│  + Add Another Zone                      │
│                                          │
│  [← Back]              [Save & Next →]   │
└──────────────────────────────────────────┘
```

---

### Screen 5 — Add First Camera

```
┌──────────────────────────────────────────┐
│  Step 4 of 4 — Camera Setup              │
│  ████████████████ 100%                   │
│                                          │
│  Zone: {selected zone name}              │
│                                          │
│  Camera Name *     [________________]    │
│  Camera Code *     [________________]    │
│  RTSP URL *        [________________]    │
│  Camera Type       [Fixed ▼]             │
│  Position          [________________]    │
│                                          │
│  [Test Connection]  ← validates RTSP URL │
│                                          │
│  + Add Another Camera                    │
│                                          │
│  [← Back]          [Complete Setup →]    │
└──────────────────────────────────────────┘
```

**RTSP Test Connection:**
- System attempts to connect to RTSP URL
- Shows: ✅ Connected (FPS: 25) or ❌ Connection Failed
- Admin can still save even if test fails (camera may be offline temporarily)

---

### Screen 6 — Setup Complete

```
┌──────────────────────────────────────────┐
│                                          │
│           ✅ Setup Complete!             │
│                                          │
│   Your VisionGuard AI platform is ready. │
│                                          │
│   Summary:                               │
│   • 1 Factory created                    │
│   • 1 Department configured              │
│   • 1 Zone configured                    │
│   • 1 Camera connected                   │
│   • AI Worker assigned automatically     │
│                                          │
│   You can add more factories, zones,     │
│   and cameras from the Admin panel.      │
│                                          │
│         [Go to Dashboard →]              │
│                                          │
└──────────────────────────────────────────┘
```

---

## 23.4 First Login Detection

System tracks two flags per user:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `is_first_login` | BOOLEAN | true | Has user logged in before? |
| `setup_completed` | BOOLEAN | false | Has setup wizard been completed? |

**Behavior:**

```
User logs in
    ↓
is_first_login = true?
    → Force password change screen
    → Set is_first_login = false
    ↓
setup_completed = false AND role = HO_ADMIN?
    → Redirect to Setup Wizard
    ↓
setup_completed = true?
    → Normal dashboard
```

---

## 23.5 Post-Setup — What HO Admin Can Do Next

After setup wizard completes, HO Admin can:

- Add more factories (no limit based on subscription)
- Add more departments to any factory
- Add more zones to any department
- Add more cameras to any zone
- Create additional users and assign roles
- Upload enterprise logo and configure branding
- Configure detection rules per zone
- Set up notification preferences
- Invite Factory Admins for each factory

---

## 23.6 Factory Admin Onboarding (After HO Admin Creates Them)

```
HO Admin creates Factory Admin user
    ↓
System sends Welcome Email to Factory Admin
    ↓
Factory Admin logs in → forced password change
    ↓
is_first_login = false (no wizard for Factory Admin)
    ↓
Factory Admin lands on their Factory Dashboard
    ↓
If factory has no departments/zones yet →
    Show banner: "Your factory has no zones configured.
                  Contact your HO Admin or add zones now."
```

---

## 23.7 Functional Requirements — Onboarding

**FR-ONB-001:** Super Admin shall be able to create a new enterprise with name, code, logo, colors, and contact details.

**FR-ONB-002:** Super Admin shall create the first HO Admin user for each enterprise during enterprise creation.

**FR-ONB-003:** System shall send a Welcome Email to newly created HO Admin with a one-time password setup link (expires in 24 hours).

**FR-ONB-004:** System shall detect first login (`is_first_login = true`) and force password change before any other action.

**FR-ONB-005:** System shall redirect HO Admin to Setup Wizard automatically if `setup_completed = false`.

**FR-ONB-006:** Setup Wizard shall guide HO Admin through: Factory → Department → Zone → Camera in sequence.

**FR-ONB-007:** Setup Wizard shall show progress indicator (step X of 4).

**FR-ONB-008:** Each step of the Setup Wizard shall validate inputs before proceeding to the next step.

**FR-ONB-009:** Camera screen shall provide a "Test Connection" button to validate RTSP URL before saving.

**FR-ONB-010:** Setup Wizard shall allow adding multiple factories, departments, zones, and cameras before completing.

**FR-ONB-011:** On Setup Wizard completion, system shall set `setup_completed = true` and redirect to dashboard.

**FR-ONB-012:** AI Worker shall be auto-assigned to cameras upon setup completion.

**FR-ONB-013:** Setup Wizard progress shall be saved at each step — if admin closes browser midway, they resume from last completed step on next login.

**FR-ONB-014:** HO Admin shall be able to re-access Setup Wizard from Admin Settings if they wish to add more entities post-setup.

**FR-ONB-015:** Factory Admin shall not see Setup Wizard — they land directly on their factory dashboard.

---

## 23.8 Database Fields — Onboarding Tracking

### Updated: identity.users

```
is_first_login       BOOLEAN DEFAULT true
setup_completed      BOOLEAN DEFAULT false
password_changed_at  TIMESTAMPTZ
invited_by           FK → identity.users
invited_at           TIMESTAMPTZ
```

### New: onboarding.setup_progress

```
id                   UUID PK
user_id              FK → identity.users
enterprise_id        FK → enterprises
last_completed_step  INT DEFAULT 0
factory_id           FK → factories (nullable — step 1 result)
department_id        FK → departments (nullable — step 2 result)
zone_id              FK → zones (nullable — step 3 result)
camera_id            FK → cameras (nullable — step 4 result)
completed_at         TIMESTAMPTZ
```

This allows resuming wizard from last completed step if admin closes browser midway.

---

## 23.9 Welcome Email Template

```
Subject: Welcome to {enterprise.name} — VisionGuard AI

[Enterprise Logo]
{enterprise.name} Safety Monitoring Platform

Hello {user.name},

Your VisionGuard AI account has been created.

Login URL:  {platform_url}/login
Email:      {user.email}
Password:   {temporary_password}

This password expires in 24 hours.
You will be prompted to set a new password on first login.

If you did not expect this email, please contact your system administrator.

— VisionGuard AI Platform
```

---

*End of First Time Setup & Onboarding Flow Section*

---

# 24. Security Enhancements

## 24.1 Two Factor Authentication (2FA)

**FR-SEC-001:** System shall support optional 2FA for all user roles via TOTP (Google Authenticator / Authy).

**FR-SEC-002:** 2FA shall be mandatory for Super Admin and HO Admin roles.

**FR-SEC-003:** User shall be able to enable/disable 2FA from their profile settings (except mandatory roles).

**FR-SEC-004:** On 2FA enable, system shall show QR code for authenticator app setup.

**FR-SEC-005:** Backup codes (8 codes) shall be generated on 2FA setup for account recovery.

## 24.2 Session Management

**FR-SEC-006:** System shall auto-logout idle users after configurable timeout (default: 30 minutes).

**FR-SEC-007:** Admin shall configure session timeout per role:

| Role | Default Timeout |
|---|---|
| Super Admin | 15 minutes |
| HO Admin | 30 minutes |
| Factory Admin | 60 minutes |
| Supervisor | 120 minutes |
| Viewer | 240 minutes |

**FR-SEC-008:** User shall see a warning popup 2 minutes before session expiry with option to extend.

**FR-SEC-009:** On session expiry, user shall be redirected to login page with message "Session expired. Please login again."

## 24.3 IP Whitelisting

**FR-SEC-010:** Enterprise Admin shall configure allowed IP ranges for their enterprise.

**FR-SEC-011:** Login attempts from non-whitelisted IPs shall be blocked and logged to audit.

**FR-SEC-012:** IP whitelist shall support individual IPs and CIDR ranges (e.g. 192.168.1.0/24).

**FR-SEC-013:** Super Admin shall bypass IP whitelist (for support access).

## 24.4 Password Expiry

**FR-SEC-014:** System shall enforce password expiry after configurable period (default: 90 days).

**FR-SEC-015:** User shall receive email reminder 7 days before password expiry.

**FR-SEC-016:** On password expiry, user shall be forced to change password before accessing platform.

**FR-SEC-017:** Last 5 passwords shall not be reusable.

---

# 25. Alert Management Enhancements

## 25.1 Full Escalation Matrix

**FR-ALT-020:** System shall support a configurable multi-level escalation matrix per severity:

| Level | Trigger | Notify |
|---|---|---|
| Level 1 | Alert created | Zone Supervisor |
| Level 2 | No ack in 5 min (High) | Department Head |
| Level 3 | No ack in 15 min (High) | Safety Officer |
| Level 4 | No ack in 30 min (High) | Factory Admin |
| Level 5 | No ack in 60 min (High) | HO Admin |

**FR-ALT-021:** Escalation matrix shall be fully configurable per enterprise per severity level.

**FR-ALT-022:** Each escalation event shall be logged to audit trail.

**FR-ALT-023:** Escalation shall stop as soon as alert is acknowledged at any level.

## 25.2 Alert Bulk Actions

**FR-ALT-024:** Supervisor shall be able to select multiple alerts and perform bulk actions:
- Bulk Acknowledge
- Bulk Assign (to a user)
- Bulk Close (with mandatory comment)

**FR-ALT-025:** Bulk actions shall be logged individually in alert history (each alert gets its own history entry).

**FR-ALT-026:** Bulk action limit: maximum 100 alerts at once.

## 25.3 False Positive Marking

**FR-ALT-027:** Supervisor shall be able to mark an alert as "False Positive" with a reason.

**FR-ALT-028:** False positive alerts shall be excluded from compliance % calculations.

**FR-ALT-029:** False positive rate shall be tracked per camera — high false positive rate triggers AI model review recommendation.

**FR-ALT-030:** False positive reasons shall be stored and used for model improvement reporting.

False positive reasons (configurable):
- Poor lighting
- Camera angle obstruction
- Reflection / glare
- Worker bending (helmet not visible)
- Other (free text)

## 25.4 Alert Snooze

**FR-ALT-031:** Supervisor shall be able to snooze alerts for a specific camera for a defined period:
- 15 minutes
- 30 minutes
- 1 hour
- 2 hours
- Custom duration

**FR-ALT-032:** Snooze reason shall be mandatory.

**FR-ALT-033:** During snooze period, no new alerts of the same type shall be created for that camera.

**FR-ALT-034:** Snooze shall auto-expire at the configured time and alerts shall resume.

**FR-ALT-035:** Snooze actions shall be logged to audit trail.

## 25.5 Alert Templates (Resolution Notes)

**FR-ALT-036:** Admin shall configure common resolution note templates:
- "Worker warned and PPE provided"
- "Worker removed from zone"
- "Camera obstruction cleared"
- "False alarm — lighting issue"

**FR-ALT-037:** Supervisor shall select a template when closing an alert (or write custom note).

---

# 26. Dashboard Enhancements

## 26.1 Full Screen Mode

**FR-DASH-010:** Dashboard shall support full screen mode for control room TV displays.

**FR-DASH-011:** Full screen mode shall auto-rotate between:
- Enterprise overview
- Factory 1 dashboard
- Factory 2 dashboard
- Alert feed

**FR-DASH-012:** Rotation interval shall be configurable (default: 30 seconds per screen).

## 26.2 Dark Mode

**FR-DASH-013:** Platform shall support Dark Mode toggle.

**FR-DASH-014:** User preference (dark/light) shall be saved per user in DB.

**FR-DASH-015:** Control room full screen mode shall default to Dark Mode.

## 26.3 Activity Feed

**FR-DASH-016:** Dashboard shall show a real-time Activity Feed panel showing last 20 events:

```
[2 min ago]  Alert resolved — Helmet Missing — Zone A — by Ravi Kumar
[5 min ago]  Zone B occupancy exceeded (8/5)
[8 min ago]  Camera CAM-003 came back online
[12 min ago] Config updated — Welding Zone threshold changed
[15 min ago] New alert — Vest Missing — Zone C
```

**FR-DASH-017:** Activity feed shall update in real time via WebSocket.

**FR-DASH-018:** Activity feed items shall be clickable — click navigates to relevant entity.

## 26.4 Dashboard Auto-Refresh

**FR-DASH-019:** User shall configure dashboard auto-refresh interval:
- Real-time (WebSocket — default)
- Every 30 seconds
- Every 1 minute
- Every 5 minutes

---

# 27. Notification Enhancements

## 27.1 SMS Notifications

**FR-NOT-010:** System shall support SMS notifications via configurable SMS gateway (Twilio / local provider).

**FR-NOT-011:** SMS shall be sent for Critical and High severity alerts only (to avoid spam).

**FR-NOT-012:** SMS template shall be concise (160 chars max):
```
[{enterprise_code}] {severity} Alert: {violation_type} at {zone_name}. 
View: {short_url}
```

## 27.2 Notification Digest

**FR-NOT-013:** User shall configure notification digest instead of individual notifications:
- Real-time (default)
- Every 15 minutes summary
- Every 1 hour summary
- Daily digest (end of day)

**FR-NOT-014:** Digest shall group alerts by severity and show count:
```
Last 1 hour summary:
  Critical: 0
  High: 3 (2 Helmet Missing, 1 Overcrowding)
  Medium: 7
  Low: 2
View all: {dashboard_url}
```

**FR-NOT-015:** Critical alerts shall always be sent immediately regardless of digest setting.

## 27.3 Do Not Disturb (DND)

**FR-NOT-016:** User shall configure DND hours (e.g. 10 PM — 6 AM).

**FR-NOT-017:** During DND, only Critical alerts shall bypass DND and notify immediately.

**FR-NOT-018:** Non-critical alerts during DND shall be queued and delivered as a digest at DND end time.

## 27.4 Notification Read/Unread Tracking

**FR-NOT-019:** In-app notifications shall show unread count badge on notification bell icon.

**FR-NOT-020:** User shall mark individual notifications as read or mark all as read.

**FR-NOT-021:** Unread notifications older than 7 days shall be auto-marked as read.

---

# 28. Reports Enhancements

## 28.1 Scheduled Email Reports

**FR-RPT-010:** Admin shall configure scheduled reports with:
- Report type
- Frequency (Daily / Weekly / Monthly)
- Delivery time
- Recipients (email list)
- Format (PDF / Excel / Both)

**FR-RPT-011:** System shall auto-generate and email scheduled reports at configured time.

**FR-RPT-012:** Failed report delivery shall retry 3 times and notify admin on all retries fail.

## 28.2 Custom Date Range Reports

**FR-RPT-013:** User shall generate reports for any custom date range (not just daily/weekly/monthly).

**FR-RPT-014:** Maximum date range for a single report: 90 days.

## 28.3 Comparative Reports

**FR-RPT-015:** System shall generate comparative reports:
- This month vs Last month
- This week vs Last week
- Factory A vs Factory B (HO Admin only)
- Zone A vs Zone B (within same factory)

**FR-RPT-016:** Comparative report shall show % change with up/down indicators.

## 28.4 Zone-wise & Camera-wise Reports

**FR-RPT-017:** User shall generate reports filtered by specific zone.

**FR-RPT-018:** User shall generate reports filtered by specific camera.

## 28.5 Data Export (CSV)

**FR-RPT-019:** User shall export raw data as CSV for:
- Violations list
- Occupancy logs
- Alert history
- Audit log

**FR-RPT-020:** CSV export shall respect user's access scope (Factory Admin gets only their factory's data).

**FR-RPT-021:** CSV filenames shall use enterprise code: `{enterprise_code}_violations_2026-01.csv`

---

# 29. Configuration Enhancements

## 29.1 Config History

**FR-CFG-010:** System shall maintain full history of zone config changes:
- What changed (old value → new value)
- Who changed it
- When it was changed

**FR-CFG-011:** Admin shall view config history per zone from settings page.

**FR-CFG-012:** Admin shall restore a previous config version with one click.

## 29.2 Config Copy

**FR-CFG-013:** Admin shall copy zone configuration from one zone to another.

**FR-CFG-014:** Admin shall copy zone configuration to multiple zones at once (bulk copy).

**FR-CFG-015:** Before copy, system shall show preview of what will change.

## 29.3 Config Templates

**FR-CFG-016:** Admin shall save a zone config as a named template:
- "Welding Zone Standard"
- "Chemical Storage High Security"
- "General Assembly Standard"

**FR-CFG-017:** Admin shall apply a saved template to any zone.

**FR-CFG-018:** Templates shall be available enterprise-wide (not factory-specific).

## 29.4 Bulk Config Update

**FR-CFG-019:** Admin shall select multiple zones and update a specific setting for all at once.

Example: Update helmet threshold from 0.75 to 0.80 for all welding zones across all factories.

**FR-CFG-020:** Bulk config update shall show confirmation with list of affected zones before applying.

---

# 30. User Management Enhancements

## 30.1 User Activity Log

**FR-USR-010:** System shall track per-user activity:
- Last login timestamp
- Last active timestamp
- Last action performed
- Total alerts resolved (count)
- Total logins (count)

**FR-USR-011:** Admin shall view user activity report from user management page.

## 30.2 Bulk User Import

**FR-USR-012:** Admin shall import users via CSV file with columns:
```
name, email, role, factory_code, department_code, zone_codes
```

**FR-USR-013:** System shall validate CSV before import and show error report for invalid rows.

**FR-USR-014:** On successful import, system shall send Welcome Email to all imported users.

**FR-USR-015:** Maximum bulk import: 500 users per file.

## 30.3 User Groups

**FR-USR-016:** Admin shall create user groups (e.g. "Welding Supervisors", "Night Shift Team").

**FR-USR-017:** Notifications shall be sendable to a user group instead of individual users.

**FR-USR-018:** Alert routing shall support assigning to a user group (any member can acknowledge).

## 30.4 Temporary Access

**FR-USR-019:** Admin shall grant temporary access to a user with auto-expiry date.

**FR-USR-020:** On expiry, account shall be auto-deactivated.

**FR-USR-021:** Admin shall receive email reminder 1 day before temporary access expires.

---

# 31. Camera & Infrastructure Enhancements

## 31.1 On-Demand Snapshot

**FR-CAM-010:** User shall request an on-demand snapshot from any active camera.

**FR-CAM-011:** On-demand snapshot shall be captured by AI worker and stored in MinIO within 5 seconds.

**FR-CAM-012:** Snapshot shall be viewable directly in dashboard and downloadable.

## 31.2 Camera Maintenance Mode

**FR-CAM-013:** Admin shall put a camera into "Maintenance Mode":
- No alerts generated during maintenance
- No offline alerts triggered
- Dashboard shows "Under Maintenance" badge

**FR-CAM-014:** Maintenance mode shall require:
- Start time
- Expected end time
- Reason

**FR-CAM-015:** On maintenance end time, camera shall auto-exit maintenance mode.

**FR-CAM-016:** Maintenance mode actions shall be logged to audit trail.

## 31.3 Camera Grouping / Views

**FR-CAM-017:** User shall create custom camera groups (e.g. "North Wing Cameras", "Entry Gates").

**FR-CAM-018:** Dashboard shall support multi-camera grid view (2×2, 3×3, 4×4) for grouped cameras.

**FR-CAM-019:** Full screen multi-camera view shall be available for control room use.

## 31.4 Bulk Camera Import

**FR-CAM-020:** Admin shall import cameras via CSV:
```
name, code, rtsp_url, zone_code, camera_type, position
```

**FR-CAM-021:** System shall validate RTSP URL format for all rows before import.

**FR-CAM-022:** Maximum bulk import: 200 cameras per file.

---

# 32. Shift Management

## 32.1 Shift Configuration

**FR-SHF-001:** Admin shall configure shifts per factory:

| Field | Example |
|---|---|
| Shift Name | Morning Shift |
| Start Time | 06:00 AM |
| End Time | 02:00 PM |
| Days | Monday to Saturday |

**FR-SHF-002:** Factory shall support up to 3 shifts (Morning / Evening / Night).

**FR-SHF-003:** Shifts shall be configurable per factory — different factories can have different shift timings.

## 32.2 Shift-wise Analytics

**FR-SHF-004:** All violations, alerts, and occupancy data shall be tagged with the active shift at time of detection.

**FR-SHF-005:** Analytics shall show shift-wise breakdown:
- Violations per shift
- Compliance % per shift
- Alert volume per shift
- Peak occupancy per shift

**FR-SHF-006:** Dashboard shall show currently active shift name and time remaining.

**FR-SHF-007:** System shall identify highest-risk shift (most violations) and highlight it in analytics.

## 32.3 Shift-wise Reports

**FR-SHF-008:** Reports shall be generatable per shift.

**FR-SHF-009:** Daily report shall include shift-wise breakdown section.

---

# 33. Camera Maintenance Management

## 33.1 Maintenance Schedule

**FR-MNT-001:** Admin shall schedule preventive maintenance for cameras:
- Camera
- Scheduled date
- Maintenance type (Cleaning / Calibration / Hardware check)
- Assigned technician
- Notes

**FR-MNT-002:** System shall send reminder notifications 24 hours before scheduled maintenance.

**FR-MNT-003:** Technician shall mark maintenance as completed with:
- Completion timestamp
- Work performed (notes)
- Next maintenance due date

## 33.2 Maintenance History

**FR-MNT-004:** System shall maintain full maintenance history per camera.

**FR-MNT-005:** Camera detail page shall show:
- Last maintenance date
- Next maintenance due
- Maintenance history log

**FR-MNT-006:** Cameras overdue for maintenance (> 90 days since last maintenance) shall show warning badge.

---

# 34. Announcements / Notice Board

## 34.1 Factory Announcements

**FR-ANN-001:** Factory Admin / HO Admin shall post announcements visible to all users in scope:

| Scope | Who Sees It |
|---|---|
| Enterprise-wide | All users in enterprise |
| Factory-wide | All users in that factory |
| Department-wide | All users in that department |

**FR-ANN-002:** Announcement fields:
- Title
- Message (rich text)
- Scope (Enterprise / Factory / Department)
- Priority (Normal / Urgent)
- Expiry date (auto-hides after expiry)

**FR-ANN-003:** Urgent announcements shall appear as a banner on top of dashboard.

**FR-ANN-004:** Normal announcements shall appear in a Notice Board panel on dashboard.

**FR-ANN-005:** Users shall acknowledge announcements (read receipt).

---

# 35. API Access for Clients

## 35.1 Client API Keys

**FR-API-001:** Enterprise Admin shall generate API keys for external integrations.

**FR-API-002:** API key shall have configurable permissions (read-only / read-write per module).

**FR-API-003:** API key shall have configurable expiry date.

**FR-API-004:** All API key usage shall be logged (endpoint, timestamp, IP).

**FR-API-005:** Admin shall revoke API keys instantly.

## 35.2 Webhook Support

**FR-API-006:** Enterprise Admin shall configure webhooks for events:
- Alert Created
- Alert Resolved
- Violation Detected
- Camera Offline

**FR-API-007:** Webhook payload shall be JSON with full event details.

**FR-API-008:** Failed webhook deliveries shall retry 3 times.

**FR-API-009:** Webhook delivery log shall be viewable from settings.

---

# 36. Shift Management DB Tables

## shifts
```
id                UUID PK
factory_id        FK → factories
enterprise_id     FK → enterprises
name              VARCHAR        (Morning Shift)
start_time        TIME           (06:00:00)
end_time          TIME           (14:00:00)
days              JSONB          (["MON","TUE","WED","THU","FRI","SAT"])
status            ENUM           (Active / Inactive)
created_on        TIMESTAMPTZ
created_by        FK → users
```

## camera_maintenance
```
id                UUID PK
camera_id         FK → cameras
enterprise_id     FK → enterprises
scheduled_date    DATE
maintenance_type  ENUM (Cleaning / Calibration / Hardware)
assigned_to       FK → users
status            ENUM (Scheduled / InProgress / Completed / Overdue)
notes             TEXT
completed_at      TIMESTAMPTZ
completed_by      FK → users
completion_notes  TEXT
next_due_date     DATE
created_on        TIMESTAMPTZ
created_by        FK → users
```

## announcements
```
id                UUID PK
enterprise_id     FK → enterprises
factory_id        FK → factories (nullable — enterprise-wide if null)
department_id     FK → departments (nullable)
title             VARCHAR
message           TEXT
priority          ENUM (Normal / Urgent)
scope             ENUM (Enterprise / Factory / Department)
expires_at        TIMESTAMPTZ
created_by        FK → users
created_on        TIMESTAMPTZ
```

## announcement_reads
```
id                UUID PK
announcement_id   FK → announcements
user_id           FK → users
read_at           TIMESTAMPTZ
```

## alert_snooze
```
id                UUID PK
camera_id         FK → cameras
zone_id           FK → zones
violation_type    ENUM
snoozed_by        FK → users
snooze_reason     TEXT
snoozed_until     TIMESTAMPTZ
created_on        TIMESTAMPTZ
```

## config_history
```
id                UUID PK
zone_id           FK → zones
enterprise_id     FK → enterprises
changed_by        FK → users
old_config        JSONB
new_config        JSONB
change_reason     TEXT
changed_at        TIMESTAMPTZ
```

## config_templates
```
id                UUID PK
enterprise_id     FK → enterprises
name              VARCHAR        (Welding Zone Standard)
description       TEXT
config_data       JSONB
created_by        FK → users
created_on        TIMESTAMPTZ
```

## user_groups
```
id                UUID PK
enterprise_id     FK → enterprises
factory_id        FK → factories
name              VARCHAR        (Night Shift Supervisors)
description       TEXT
created_by        FK → users
created_on        TIMESTAMPTZ
```

## user_group_members
```
id                UUID PK
group_id          FK → user_groups
user_id           FK → users
added_by          FK → users
added_on          TIMESTAMPTZ
```

## api_keys
```
id                UUID PK
enterprise_id     FK → enterprises
name              VARCHAR
key_hash          VARCHAR        (SHA-256, never plaintext)
permissions       JSONB
expires_at        TIMESTAMPTZ
last_used_at      TIMESTAMPTZ
status            ENUM (Active / Revoked)
created_by        FK → users
created_on        TIMESTAMPTZ
```

---

*End of Enhancement Sections*
