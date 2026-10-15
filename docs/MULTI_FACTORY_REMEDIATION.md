# Multi-factory remediation plan and session handoff

Updated: 2026-10-15. Review baseline: `0051fde`.

This file is persistent project memory. Read it before continuing fleet-readiness work and update status, evidence and remaining risks after each implementation. It does not assert that chat memory persists between sessions.

## Agreed deployment context

- Approximately 200 cameras per factory; multiple factories, 500+ cameras growing to 1,000+.
- Existing DVR/NVR retains continuous recordings. VisionGuard processes live feeds for violations and retains incident evidence.
- Use English for source, documentation, commits and GitHub changes; user-facing explanations may be Hinglish.
- Existing webcam trials use a separate six-class ONNX model. False helmet/vest detections were observed. Production nine-class model accuracy and GPU camera capacity remain unmeasured.
- Factory-local processing with central oversight is the intended direction, not an existing guarantee of offline operation.

## Priority order and acceptance gates

| Priority | Work | Acceptance evidence | Status |
| --- | --- | --- | --- |
| P1 | Factory-bound worker scheduling, explicit measured camera limits, concurrent admission control, pending-camera backfill | No foreign factory/tenant assignments; last-slot races cannot exceed limits; offline/unconfigured workers receive no new assignments; pending cameras resume once capacity is available | Implemented and locally verified |
| P2 | Durable edge incidents and evidence retries; remove synchronous snapshot dependency; cached startup configuration | Short-lived incident survives broker/storage outage and process restart; replay keeps stable event IDs; bounded storage and explicit full-disk behavior | Pending |
| P3 | Independent capture, bounded latest-frame handoff and frame-age checks; isolate blocking operations | Slow inference/storage and a stalled stream do not accumulate stale detections or stall healthy cameras; reconnect and shutdown tests | Pending |
| P4 | Actual GPU/model readiness and production fail-closed GPU startup | Required CUDA absence fails startup; heartbeat reports actual runtime state; model startup and device checks tested on target GPU | Pending |
| P5 | Automatic failed-worker recovery with ownership leases/fencing | Worker loss recovers within agreed RTO; partitions/recovery never cause duplicate active ownership; standby respects locality and capacity | Pending |
| P6 | Batch assignment/configuration reads and fleet monitoring | Assignment-query count does not grow per camera; every worker registered in monitoring; representative API/broker/database load measured | Partial: batch reads verified; fleet monitoring/load pending |
| P7 | Site deployment, shared-service recovery, production model/data validation and staged rollout | DVR compatibility; independent labels; 24-hour integrated soak; restore/failure drills; measured hardware sizing at 10–20, then 50–100, then 200 cameras per factory | Pending; needs site hardware/data |

P1 pending-camera backfill is not automatic failover. Do not reassign stale-worker cameras without ownership fencing. A camera limit is an operator-supplied admission budget established by measurements, not an automatically discovered hardware capability.

## Current implementation decisions

- Start with P1 as a reviewable, separately tested release; keep every later priority visible here.
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

Next implementation: P2. Start with `ai-worker/src/events/publisher.py` and `ai-worker/src/pipeline/camera_worker.py`: persist stable incident IDs and evidence locally before network publication, retry storage independently, then add bounded replay and restart/outage tests. Review `main.py` startup ordering before adding cached configuration. Do not claim offline autonomy while these paths remain synchronous. P3–P7 remain as listed above; production GPU/site evidence cannot be manufactured in this workspace.
