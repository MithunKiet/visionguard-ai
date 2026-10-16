# VisionGuard AI — Project Context

Enterprise-grade, multi-tenant Factory Safety Monitoring SaaS platform. **Production readiness is tracked in `docs/REVIEW_FIXES.md`; remaining pilot and deployment gates must be completed.** You are the long-term maintainer, not a rewrite author.

## Ground rules

- Do NOT redesign the architecture unless absolutely necessary.
- Understand the complete codebase, affected module, and its dependencies before changing anything.
- Never modify working functionality without justification.
- Never change architecture unless there is a measurable benefit.
- Maintain backward compatibility. Follow existing project conventions (see naming below).
- Treat this as an enterprise production application, not a prototype.
- When proposing a change of any real size: explain why, explain the impact, list affected files, explain the risks — and wait for approval before implementing large refactors.

## Naming convention

**Always snake_case** for DB columns, Python identifiers, and schema-facing fields — never PascalCase or camelCase. This applies to every new migration, model column, and Pydantic field.

## Business purpose

Continuously monitors factory floor CCTV cameras with AI. Detects: helmet / safety-vest / gloves / shoe / face-mask violations, overcrowding, and configurable future PPE types.

Pipeline (already fully working, verified end-to-end):

```
Camera → AI Detection → Violation → Alert → Notification → Dashboard → Reports → Analytics
```

## Technology stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Clean Architecture (`api/ application/ domain/ infrastructure/` per module)
- **Frontend**: React, TypeScript, Vite, Material UI, TanStack Query
- **AI Workers**: Python, YOLO, RabbitMQ, RTSP camera streams, real-time detection
- **Infra**: Docker Compose — PostgreSQL, RabbitMQ, Redis, MinIO, MediaMTX, Prometheus, Grafana

## Database design

Every table follows the BaseEntity pattern:

- `id` — internal integer PK. Never expose via API, JWT, or URLs.
- `public_id` — UUID. Used everywhere outside the database: API, JWT, frontend, external integrations, reports, imports/exports.
- All foreign keys use internal integer ids for performance; only repository code at the literal SQL boundary translates a `public_id` to/from the internal integer (helpers in `backend/src/shared/database/pid.py`: `to_pk`, `to_public_id`, `to_pks`).
- Exception: `identity.user_roles` is a pure link table, not a BaseEntity — composite PK of `user_public_id`/`role_public_id` directly (no surrogate id, no audit columns). Protocol tables such as event receipts and `worker.camera_leases` also use explicit keys; lease tokens/generations are retained ownership history, not user-managed entities.

Current migration head: **0020**.

## Multi-tenancy

Hierarchy: **Enterprise → Factory → Department → Zone → Camera**. Every table is scoped by `enterprise_id`. No data leakage across tenants is allowed. Data-visibility scoping (`shared/security/scope.py`) is layered on top of role-based access — e.g. a FACTORY_MANAGER only sees their own factory's data even though RBAC alone would let the endpoint through.

## Core modules

Identity (auth/users/roles/permissions), Factories, Departments, Zones, Cameras, PPE Catalog, Zone Detection Configuration, Violations, Alerts, Notifications, Occupancy, Shifts, Maintenance Mode, Reports, Analytics, Audit Trail.

## Alerts

Lifecycle: `Open → Acknowledged → Resolved | FalsePositive`. Supports SLA tracking (severity-based due times).

## Notifications

Email, Slack, Webhook, Desktop.

## Roles

`SYSTEM_ADMIN`, `ENTERPRISE_ADMIN`, `FACTORY_MANAGER`, `SAFETY_OFFICER`, `SUPERVISOR`, `VIEWER`. A user may hold multiple roles simultaneously — authorization checks for intersection, not equality (`require_roles()`). Role-based access is combined with data-visibility rules (e.g. a Factory Manager can only access their assigned factory's data).

## Current status (verified)

Multi-factory remediation priorities, deployment context and implementation handoff are tracked in [docs/MULTI_FACTORY_REMEDIATION.md](docs/MULTI_FACTORY_REMEDIATION.md). Read and update that plan when continuing fleet-readiness work. P1 factory/capacity scheduling, P2 durable local incidents and P3 capture isolation/local freshness checks are implemented and locally tested; P4 model/device startup guards are also implemented; target-GPU acceptance remains pending. See [docs/MODEL_READINESS.md](docs/MODEL_READINESS.md) for the required production model checksum, warmup and truthful heartbeat contract. P5 ownership leases, automatic local failover and transactional event fencing are implemented; see [docs/WORKER_FAILOVER.md](docs/WORKER_FAILOVER.md) for the mandatory coordinated rollout, bounded offline authorization and remaining site failure-drill gates. P6 fleet monitoring/load validation is the next priority. See [docs/CAPTURE_ISOLATION.md](docs/CAPTURE_ISOLATION.md) for per-camera subprocesses, 1080p default frame budget and the distinction between local decode age and camera-origin age. See [docs/DURABLE_EDGE_EVENTS.md](docs/DURABLE_EDGE_EVENTS.md) before changing worker lifecycle, persistent volumes or replay semantics.

Automated unit/integration/browser checks and a synthetic event/report smoke validate the implemented paths. Alert delivery now uses a transactional PostgreSQL outbox with bounded retries and administrator replay; see `docs/ALERT_DELIVERY.md`. Live video uses a per-asset authenticated HLS gateway; see `docs/SECURE_LIVE_VIDEO.md` for required private relays and camera mappings. Real-camera model accuracy, GPU capacity, real-camera media/TLS validation, provider/load validation, production TLS and backup/restore validation remain required. See `docs/REVIEW_FIXES.md` for evidence and per-finding status.
