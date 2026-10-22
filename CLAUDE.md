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

Current migration head: **0026**.

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

Multi-factory remediation priorities, deployment context and implementation handoff are tracked in [docs/MULTI_FACTORY_REMEDIATION.md](docs/MULTI_FACTORY_REMEDIATION.md). Read and update that plan when continuing fleet-readiness work. P1 factory/capacity scheduling, P2 durable local incidents and P3 capture isolation/local freshness checks are implemented and locally tested; P4 model/device startup guards are also implemented; target-GPU acceptance remains pending. See [docs/MODEL_READINESS.md](docs/MODEL_READINESS.md) for the required production model checksum, warmup and truthful heartbeat contract. P5 ownership leases, automatic local failover and transactional event fencing are implemented; see [docs/WORKER_FAILOVER.md](docs/WORKER_FAILOVER.md) for the mandatory coordinated rollout, bounded offline authorization and remaining site failure-drill gates. P6 fleet discovery/coverage gates and synthetic control-plane measurement tools are implemented; see [docs/FLEET_MONITORING.md](docs/FLEET_MONITORING.md) and the roadmap evidence for the measured poll-lock optimization. Production requires `FLEET_TARGETS_DIR`; use the current migration head listed above. P7 tooling is prepared; site deployment/accuracy/soak/recovery acceptance, real fleet coverage and sustained production load still need measurement. See [docs/CAPTURE_ISOLATION.md](docs/CAPTURE_ISOLATION.md) for per-camera subprocesses, 1080p default frame budget and the distinction between local decode age and camera-origin age. See [docs/DURABLE_EDGE_EVENTS.md](docs/DURABLE_EDGE_EVENTS.md) before changing worker lifecycle, persistent volumes or replay semantics.

P7 acceptance tooling and the staged site runbook are now implemented; see [docs/FACTORY_PILOT_ACCEPTANCE.md](docs/FACTORY_PILOT_ACCEPTANCE.md) and `infra/pilot/acceptance.py`. The owner confirmed on 2026-10-18 that hardware and factory access are not ready. P7 remains physically unvalidated: the evidence checker only prepares a human review and always retains `production_approved=false`. Do not manufacture pilot results, approve production or infer live-camera capacity from synthetic workload tests. Keep the contract/evidence templates unfilled until actual observations exist.

The owner subsequently identified a laptop test candidate: RTX 2000 Ada Laptop GPU, 8,188 MiB VRAM, NVIDIA driver 595.95. `check-gpu-windows.cmd` prepares a separate CUDA runtime smoke check; see [docs/WINDOWS_GPU.md](docs/WINDOWS_GPU.md). Local GPU execution is pending the owner's report. This is not a factory capacity result, a PPE model-readiness report or a change to the CPU webcam trial.

The owner deferred the laptop test and requested independent pending fixes. Browser live-feed recovery now uses one authenticated-shell connection, coalesced event-driven query refreshes, HTTP snapshot resync after reconnect and 60-second browser-receipt occupancy expiry. See [docs/LIVE_FEED_RECOVERY.md](docs/LIVE_FEED_RECOVERY.md). Preserve session cleanup and the slow in-flight response regression; HTTP snapshots do not provide durable WebSocket event replay.

User administration now uses bounded server pagination (20 default, 100 maximum), scoped counts and one role query per page. The frontend follows the new metadata; API consumers must paginate to retrieve the full directory. See [docs/USER_DIRECTORY_SCALING.md](docs/USER_DIRECTORY_SCALING.md). Preserve the four-SELECT one-versus-100-row regression and role completeness on detail/invite/update paths.

Flow 1 adds transactional zone configuration delivery and current-lease application confirmations in migration 0021. See [docs/CONFIG_DELIVERY.md](docs/CONFIG_DELIVERY.md). Saves and restores commit policy/history/outbox atomically, publication retries across process failures, and worker HTTP reconciliation repairs missed pushes. Broker acceptance must never be presented as application. Keep the monotonic HTTP-versus-push regression, scoped status, lease/session/zone/version validation, confirmation expiry and constant-query batch acknowledgement. The zone PPE dialog tracks application while open. Per-camera overrides/activation and model/site validation retain their separate contracts. Both startup and readiness use the shared schema-head constant.

Flow 2 adds durable report jobs and the Reports page in migration 0022. See [docs/REPORT_JOBS.md](docs/REPORT_JOBS.md). Generate returns 202 with a queued job; consumers must follow status and paginate history. Preserve tenant/admin boundaries, idempotent request admission, attempt fencing, subprocess deadlines/reaping, bounded automatic retries and download gating. PDF caps at 5,000 rows and write-only Excel at 50,000; excess fails explicitly. The real subprocess/MinIO-SDK smoke uses a local S3 protocol fixture; real MinIO/TLS/provider validation remains separate. Startup/readiness now require 0022 and the report dispatcher.

Flow 3 adds current detection evidence in migration 0023, scoped dashboard warnings and the Detection health page. See [docs/DETECTION_HEALTH.md](docs/DETECTION_HEALTH.md). Heartbeats/activation must never substitute for fresh, current-policy inference under a valid camera lease. Preserve expiry, pause/maintenance visibility, database-wait age accounting, old-worker compatibility and the four-query health service contract (excluding authentication/scope resolution). Current-only evidence cannot establish historical coverage: safety score is null/unavailable, and compliance rates with zero denominators are null. API clients must handle these changes. Do not fabricate historical uptime, site accuracy or external paging results. Startup/readiness use schema 0023.

Flow 4 adds corrective plans, responsible reviewers, action due dates/overdue filtering, immutable current-plan photo evidence and completion/closure gates in migration 0024. See [docs/CORRECTIVE_ACTIONS.md](docs/CORRECTIVE_ACTIONS.md). Preserve transactional typed history, shared incident-row locks, optimistic revisions, eligibility/scope checks and original upload identity across uncertain replies. Plan/reassignment changes invalidate completion and require evidence attached to the new plan version; identical legacy assignment is a no-op. Photo downloads recheck access and hashes through the API; no permanent corrective-photo URLs are issued. Keep photo/body/pixel/quota limits and avoid deleting objects on ambiguous commits. Pillow 12.3.0 is a direct pinned backend requirement. Startup/readiness require 0024; physical correction and provider/site validation remain human/deployment gates.

Automated unit/integration/browser checks and a synthetic event/report smoke validate the implemented paths. Alert delivery now uses a transactional PostgreSQL outbox with bounded retries and administrator replay; see `docs/ALERT_DELIVERY.md`. Live video uses a per-asset authenticated HLS gateway; see `docs/SECURE_LIVE_VIDEO.md` for required private relays and camera mappings. Real-camera model accuracy, GPU capacity, real-camera media/TLS validation, provider/load validation, production TLS and backup/restore validation remain required. See `docs/REVIEW_FIXES.md` for evidence and per-finding status.

Flow 5 adds opt-in encrypted TOTP enrollment, password/code-confirmed disable, replay protection, MFA refresh/session checks and a database append-only audit trigger in migration 0025. See [docs/ACCOUNT_SECURITY.md](docs/ACCOUNT_SECURITY.md). Preserve existing factory/tenant authorization, initial-password restrictions, transactional MFA audit inserts and security-version session invalidation. MFA remains opt-in; self-service recovery, separate encryption-key rotation and complete durable audit coverage remain pending. JWT secret rotation requires planned authenticator recovery/re-enrollment. Upgrade API replicas together before enrollment.

Flow 6 adds verified PostgreSQL/object bundles and isolated restore drills; see [docs/BACKUP_RECOVERY.md](docs/BACKUP_RECOVERY.md). No schema migration is added (head 0025). Preserve exported-snapshot counts/references, private opaque artifact paths, completion-only manifests, independent manifest checksum checks, new-only restore destinations, native error-stopping transaction restore and object read-back verification. The old destructive timestamp-only restore interface is removed. Never start application dispatchers or factory connections as part of this drill, and never infer service RPO/RTO from file restore duration. Broker/worker state, deployment secrets, offsite encryption, enabled schedules and actual provider/site acceptance remain separate.

Flow 7 adds bounded CSV camera preview/import and durable replay receipts (migration 0026); see [docs/CAMERA_ONBOARDING.md](docs/CAMERA_ONBOARDING.md). Preserve scoped validation, per-enterprise inventory serialization, atomic audit/receipt/camera writes and explicit activation: imported cameras have is_active=false and no worker until activation opens admission. Credentials must not enter preview, receipts, logs or process arguments. Connection probes use disposable children with a 12-second timeout and two concurrent probes per API event loop. This does not validate PPE accuracy or production camera capacity.

Flow 8 adds opt-in server-side camera pagination and literal name/code search. The Cameras UI requests 50 rows, resets search to page one and recovers after inventory shrinkage. Keep no-parameter legacy list behavior for existing clients and apply identical scope/filter predicates to counts and rows. No schema change; head remains 0026. See docs/CAMERA_ONBOARDING.md for pagination consistency limits.

PPE accuracy follow-up: the owner confirmed no labeled dataset is available. `evaluate-ppe-windows.cmd <manifest> --check-dataset` now validates local six-class trial data and reports coverage without model weights/inference. Preserve explicit unmeasured/unapproved flags; synthetic regression fixtures do not establish accuracy. See docs/PPE_ACCURACY_EVALUATION.md for collection, labeling, split independence and acceptance steps. Actual labeled factory evaluation remains blocked on data, not completed.

GPU capacity follow-up: `benchmark-gpu-windows.cmd` prepares a separate ignored `.venv-capacity`, runs a bounded CUDA smoke and sweeps production-checkpoint inference at 1/2/4/8 camera equivalents, 2 FPS, 120 seconds/level. Requires trusted nine-class weights/hash and representative local stills; no labels needed for timing. Preserve no-CPU-fallback and inference-only boundaries. Reports distinguish allocated/reserved/device VRAM and nonmonotonic levels; deployment budget stays null. Actual Windows/GPU execution and live-camera capacity remain pending. See docs/WINDOWS_GPU.md.

Helmet/vest model selection: see docs/PPE_MODEL_SELECTION.md. YOLOv8s remains an architecture candidate; no production artifact/license approval exists. Current runtime requires exact nine-class mapping. Do not pad/relabel an incompatible five/six-class model. Training now uses camera/session-grouped train/val/test manifests and unique candidate-only outputs, with no runtime weight copy. Preserve sealed held-out test data, strict input/hash checks and explicit separate deployment. User-reported laptop CUDA smoke passed, but model execution/accuracy/capacity remain unmeasured.
