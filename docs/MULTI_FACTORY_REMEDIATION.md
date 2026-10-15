# Multi-factory remediation plan and session handoff

Updated: 2026-10-15. Review baseline: `0051fde`.

This file is persistent project memory. Read it before continuing fleet-readiness work and update status, evidence and remaining risks after each implementation. It does not assert that chat memory persists between sessions.

## Agreed deployment context

- Approximately 200 cameras per factory; multiple factories, 500+ cameras growing to 1,000+.
- Existing DVR/NVR retains continuous recordings. VisionGuard processes live feeds for violations and retains incident evidence.
- Use English for source, documentation, commits and GitHub changes; user-facing explanations may be Hinglish.
- Existing webcam trials use a separate six-class ONNX model. False helmet/vest detections were observed. Production nine-class model accuracy and GPU camera capacity remain unmeasured.
- Factory-local processing with central oversight is the intended direction. P2 adds durable local incidents and time-limited cached assignments; extended offline autonomy and site outage validation remain pending.

## Priority order and acceptance gates

| Priority | Work | Acceptance evidence | Status |
| --- | --- | --- | --- |
| P1 | Factory-bound worker scheduling, explicit measured camera limits, concurrent admission control, pending-camera backfill | No foreign factory/tenant assignments; last-slot races cannot exceed limits; offline/unconfigured workers receive no new assignments; pending cameras resume once capacity is available | Implemented and locally verified |
| P2 | Durable edge incidents and evidence retries; remove synchronous snapshot dependency; cached startup configuration | Short-lived incident survives broker/storage outage and process restart; replay keeps stable event IDs; bounded storage and explicit full-disk behavior | Implemented and locally verified |
| P3 | Independent capture, bounded latest-frame handoff and frame-age checks; isolate blocking operations | Slow inference/storage and a stalled stream do not accumulate stale detections or stall healthy cameras; reconnect and shutdown tests | Pending |
| P4 | Actual GPU/model readiness and production fail-closed GPU startup | Required CUDA absence fails startup; heartbeat reports actual runtime state; model startup and device checks tested on target GPU | Pending |
| P5 | Automatic failed-worker recovery with ownership leases/fencing | Worker loss recovers within agreed RTO; partitions/recovery never cause duplicate active ownership; standby respects locality and capacity | Pending |
| P6 | Batch assignment/configuration reads and fleet monitoring | Assignment-query count does not grow per camera; every worker registered in monitoring; representative API/broker/database load measured | Partial: batch reads verified; fleet monitoring/load pending |
| P7 | Site deployment, shared-service recovery, production model/data validation and staged rollout | DVR compatibility; independent labels; 24-hour integrated soak; restore/failure drills; measured hardware sizing at 10–20, then 50–100, then 200 cameras per factory | Pending; needs site hardware/data |

P1 pending-camera backfill is not automatic failover. Do not reassign stale-worker cameras without ownership fencing. A camera limit is an operator-supplied admission budget established by measurements, not an automatically discovered hardware capability.

## Current implementation decisions

- P1 and P2 are implemented as separately tested releases; keep every later priority visible here.
- Bind each worker to one factory; allow multiple workers in the same factory. A worker heartbeat must not grant itself factory scope or increase capacity.
- Factory/capacity configuration is administrator-controlled and tenant-scoped.
- New/legacy workers have no scheduling permission until explicitly configured. Existing assignment rows must not silently grant cross-factory stream access after upgrade.
- Count inactive assigned cameras against the limit because current readers remain connected when detection is disabled.
- Serialize scheduling decisions in PostgreSQL, across API processes; no in-memory-only capacity counter.
- Preserve existing assignments where valid. Keep overflow/unassigned cameras pending rather than borrowing another factory's workers.
- Batch camera/config reads as part of the scheduling path to remove the reviewed per-camera SQL amplification.

## Evidence and next handoff

Review reproduced locality-blind assignment and snapshot upload preventing event publication using isolated probes. The baseline passed 42 targeted AI and 30 targeted backend tests; this is not a camera capacity result.

P1 implemented in migration `0019`, `WorkerSchedulingRepository`, administrator scheduling API and the worker assignment reader. See [WORKER_SCHEDULING.md](WORKER_SCHEDULING.md) for the coordinated upgrade, API request and rollback procedure. Legacy workers receive no streams until explicitly configured. Readiness now requires schema 0019.

Validation on 2026-10-15:

- Full backend run: 127 passed and one optional synthetic MediaMTX relay smoke skipped because no relay URL was configured.
- Final scheduling suite after adding inactive-parent and ownership-retention checks: 20 passed (the full run included the original 17). Cases include real concurrent PostgreSQL sessions, factory/tenant isolation, capacity/policy races, API authorization, pending backfill and one-query retrieval of 200 camera configurations.
- AI regression suite: 88 passed, including optional pinned ONNX smoke checks. No AI implementation changed in P1.
- Backend/capacity lint, production Compose validation and whitespace checks passed.
- Migration upgrade, downgrade to 0018 and re-upgrade to 0019 succeeded on the disposable test database; schema readiness and default policy values were verified.
- Frontend and real GPU/DVR/load tests were not run for this backend change. Existing dependency deprecation warnings remain. GitHub Actions results must be checked separately.

P2 implemented in the worker SQLite journal, independent event/evidence delivery loops, bounded assignment cache and persistent per-worker Compose volumes. See [DURABLE_EDGE_EVENTS.md](DURABLE_EDGE_EVENTS.md) for acceptance semantics, upgrade/recovery, storage budgets, authorization expiry and limitations. No new migration is required.

P2 validation on 2026-10-15:

- AI suite: 112 passed, including real RabbitMQ confirmations/unroutable messages, pinned ONNX smoke, abrupt process exit/reopen, independent outage retries, full-disk rejection without cooldown acknowledgment and cached startup/revocation cases.
- Selected backend integration suites: 48 passed against PostgreSQL, including durable replay producing one violation/alert with the original event timestamp and key, plus notification-outbox regressions.
- Configured lint, production Compose validation, Prometheus semantic rule tests and whitespace checks passed. Existing dependency deprecation warnings remain.
- Evidence-store failures were simulated. No production GPU image rebuild, real camera/DVR outage drill, physical power-loss test, production object-store test or fleet-capacity measurement was performed. GitHub Actions results must be checked separately.

Next implementation: P3. Separate camera capture from inference with a bounded latest-frame handoff, validate source-frame age, and isolate stalled streams/blocking native operations. Preserve P2 local acceptance and replay semantics. P4–P7 remain as listed above; production GPU/site evidence cannot be manufactured in this workspace.
