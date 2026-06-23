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
* Scales to 100-200 cameras initially
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
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│             RabbitMQ               │
│         Event Communication        │
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│           AI Worker Pool           │
│ OpenCV + RT-DETR + ByteTrack       │
└────────────────┬───────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│           RTSP Cameras             │
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

Example:

```text
/api/v1/factories
/api/v1/zones
/api/v1/cameras
/api/v1/alerts
/api/v1/reports
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
```

---

## Infrastructure Layer

Contains:

* PostgreSQL
* RabbitMQ
* Redis
* File Storage
* External Services

---

# Event Driven Architecture

AI workers NEVER access database.

AI workers ONLY publish events.

Backend consumes events.

---

## Event Flow

```text
Camera

↓

AI Detection

↓

Event Creation

↓

RabbitMQ

↓

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

AlertCreated
```

Example:

```json
{
  "event": "helmet_missing",
  "camera_id": "CAM-001",
  "zone_id": "ZONE-01",
  "timestamp": "2026-01-01T10:00:00"
}
```

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

---

## Detection Pipeline

```text
RTSP Stream

↓

Frame Capture

↓

Frame Sampling

↓

RT-DETR Detection

↓

ByteTrack Tracking

↓

Occupancy Calculation

↓

PPE Validation

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

# Database Architecture

Database:

PostgreSQL

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

analytics

reports
```

---

## Core Tables

### identity.users

```text
Id
Name
Email
PasswordHash
RoleId
Status
```

### factory.factories

```text
Id
Name
Code
Location
Status
```

### zone.zones

```text
Id
FactoryId
Name
MaxOccupancy
SupervisorId
```

### camera.cameras

```text
Id
ZoneId
Name
RTSPUrl
Status
```

### occupancy.logs

```text
Id
ZoneId
CurrentCount
Timestamp
```

### ppe.violations

```text
Id
ZoneId
CameraId
ViolationType
SnapshotPath
CreatedOn
```

### alerts.alerts

```text
Id
ViolationId
Severity
Status
CreatedOn
```

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

---

## Camera Dashboard

Displays:

* Camera Health
* FPS
* Online Status

---

## Analytics Dashboard

Displays:

* Trends
* KPIs
* Monthly Reports

---

# Security Architecture

Authentication:

JWT

Authorization:

Role Based Access Control

Roles:

* Admin
* Supervisor
* Safety Officer
* Viewer

---

# Notification Architecture

Channels:

* Email
* In-App Notifications
* Web Notifications

Flow:

```text
Violation

↓

Alert

↓

Notification

↓

Supervisor
```

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
AI Worker
```

---

## Production (100 Cameras)

### Server 1

```text
React

FastAPI

PostgreSQL

RabbitMQ

Redis
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
```

---

## 1000 Cameras

```text
API Gateway

Backend Cluster

RabbitMQ Cluster

PostgreSQL Cluster

Redis Cluster

50+ AI Workers
```

No rewrite required.

Only horizontal scaling.

---

# Technology Stack

Frontend

* React
* TypeScript
* Material UI
* AG Grid

Backend

* FastAPI
* SQLAlchemy
* Alembic

Database

* PostgreSQL

Messaging

* RabbitMQ

Cache

* Redis

AI

* OpenCV
* RT-DETR
* ByteTrack
* PyTorch

Monitoring

* Prometheus
* Grafana
* Loki

Deployment

* Docker
* Docker Compose

Future

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

End of Document
