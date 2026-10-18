# Multi-factory remediation plan and session handoff

Updated: 2026-10-18. Review baseline: `0051fde`.

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
| P3 | Independent capture, bounded latest-frame handoff and local decode-age checks; isolate blocking operations | Slow inference/storage and a stalled stream do not accumulate stale detections or stall healthy cameras; reconnect and shutdown tests | Implemented and locally verified; upstream age needs site validation |
| P4 | Actual GPU/model readiness and production fail-closed GPU startup | Required CUDA absence fails startup; heartbeat reports actual runtime state; model startup and device checks tested on target GPU | Guards implemented and locally verified; target GPU acceptance pending |
| P5 | Automatic failed-worker recovery with ownership leases/fencing | Worker loss recovers within agreed RTO; partitions/recovery never cause duplicate active ownership; standby respects locality and capacity | Implemented and locally tested; site RTO and infrastructure failure drills pending |
| P6 | Batch assignment/configuration reads and fleet monitoring | Assignment-query count does not grow per camera; every worker registered in monitoring; representative API/broker/database load measured | Tools and local synthetic measurements implemented; real fleet inventory/coverage and site load gates pending |
| P7 | Site deployment, shared-service recovery, production model/data validation and staged rollout | DVR compatibility; independent labels; 24-hour integrated soak; restore/failure drills; measured hardware sizing at 10–20, then 50–100, then 200 cameras per factory | Acceptance tooling/runbook implemented and locally tested; physical acceptance blocked on hardware/site access/model/data |

P1 pending-camera backfill is not automatic failover. Do not reassign stale-worker cameras without ownership fencing. A camera limit is an operator-supplied admission budget established by measurements, not an automatically discovered hardware capability.

## Current implementation decisions

- P1–P3, the P4 startup/runtime guards and P5 ownership leases are implemented as separately tested releases; keep every later priority visible here.
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

P3 implemented with one supervised capture process per assigned camera, bounded shared/latest-frame slots, local decode-age deadlines and a dedicated inference executor. See [CAPTURE_ISOLATION.md](CAPTURE_ISOLATION.md) for process lifecycle, settings, memory sizing, timestamp semantics and upgrade requirements. No migration is required. The default shared slot supports 1080p BGR; larger feeds require an explicit memory budget.

P3 validation on 2026-10-15:

- AI suite: 131 passed, including spawned children stuck during open/read/release or holding a lock; reconnect without overlapping old children; healthy-camera progress; slow-consumer replacement; FPS changes; cancellation/revocation cleanup; stale/config-displaced result rejection; dedicated inference execution; existing RabbitMQ and ONNX checks.
- Native OpenCV/FFmpeg smoke passed using a generated 320x240, 20 FPS RTSP source served by local MediaMTX 1.12.3. This measures local handoff behavior, not factory-camera freshness or capacity.
- The PostgreSQL edge replay regression passed. Configured lint, production Compose checks, Prometheus semantic checks and whitespace checks passed.
- Frame age begins after local decode. Camera/DVR buffering, frozen-scene replay, real exposure timestamps, production GPU/image validation and integrated fleet soak remain unverified. Measure whole-process-tree resources: capture children add CPU/RAM beyond parent worker metrics. Native GPU hangs still require worker recovery. GitHub Actions results must be checked separately.

P4 startup/runtime guards implemented: production requires a pinned local nine-class checkpoint and CUDA, verifies model/predictor device placement through warmup, and reports observed device/artifact identity. Native loading runs on the inference executor. A bounded preflight command records startup evidence without cameras or alerts. See [MODEL_READINESS.md](MODEL_READINESS.md) for new production environment requirements and the GPU acceptance workflow. Schema remains 0019.

P4 validation on 2026-10-16:

- Main AI suite: 156 passed, two optional tests skipped (RTSP and real CPU-model smoke). Existing real RabbitMQ and trial ONNX checks ran.
- Actual CPU-model smoke passed separately using pinned PyTorch 2.5.1+cpu / torchvision 0.20.1+cpu / Ultralytics 8.3.50 and locally generated untrained nine-class test weights. The real probe successfully loaded/warmed the CPU model and rejected a CUDA request on the CPU-only runner. This is execution evidence, not accuracy validation or a production model artifact.
- 23 PostgreSQL integration tests passed, covering existing scheduling isolation/concurrency, heartbeat artifact/device round trips and edge replay. Lint, production Compose and Prometheus semantic checks passed. Existing backend dependency deprecation warnings remain; GitHub Actions results must be checked separately.
- Actual target-GPU acceptance is still pending. Production GPU image/dependency compatibility, CUDA warmup on the chosen host, reviewed production weights, accuracy/capacity and forced recovery from a native hang remain unverified. Model readiness is not a distributed ownership lease. Preserve this external gate even when moving to the next code priority.

P5 implemented on 2026-10-16 in migration `0020`: 90-second process-bound camera leases, five-second local stop margin, suspend-aware deadlines, independent capture expiry, factory/capacity-constrained automatic takeover and transactional event fencing. Old valid incidents retain their original grant across durable replay; stale telemetry/post-expiry observations are rejected. Legacy unleased assignments are never stolen. See [WORKER_FAILOVER.md](WORKER_FAILOVER.md) for coordinated upgrade/drain/rollback, the recovery budget and infrastructure assumptions.

P5 local validation:

- Full backend suite: 148 passed, two optional integration checks skipped (synthetic live-video relay and isolated notification RabbitMQ queue). After the final fail-closed history guard and additional regression cases, 19 targeted PostgreSQL failover/replay tests passed.
- Full AI suite: 169 passed, two optional checks skipped (native RTSP and real CPU-model startup); real RabbitMQ and trial ONNX tests ran. Final targeted worker lease suite: 17 passed, including expired/previous-process/legacy cached assignment rejection and child-watchdog renewal without reconnect.
- Migration 0019 → 0020 → 0019 → 0020 and schema readiness passed on the disposable database. Configured lint, production Compose validation, Prometheus rule evaluation and whitespace checks passed. Existing backend dependency deprecation warnings remain; GitHub Actions must be checked separately.

Site RTO, spare-capacity measurements, physical RTSP fencing under arbitrary host/kernel failures, authoritative database recovery and the integrated failure drill remain unverified. Backend/API outage deliberately stops leased detection after expiry; cached assignments cannot authorize longer offline operation or restart.

P6 implemented on 2026-10-16: validated operator fleet inventory, atomic Prometheus file discovery, registry/target/runtime-identity coverage audit, missing-identity alert, fixed-arrival external read workload and an isolated synthetic API/broker/PostgreSQL measurement tool. Production now requires `FLEET_TARGETS_DIR`; see [FLEET_MONITORING.md](FLEET_MONITORING.md). No new database migration is required (head remains 0020).

A measured renewal bottleneck was fixed: leased polls now perform one admission/acquisition pass under the existing policy lock, and lock only owned, pending, expired or inconsistent camera rows. They no longer load/lock another worker's live cameras. Expired takeover still waits for an event transaction holding that camera; tenant/factory/capacity fencing and historical replay checks remain in place. Full lease-poll SELECT count is constant between 1 and 200 cameras.

P6 local measurements (synthetic metadata, not video):

- Five factories × 200 camera records, 20 simulated workers, 1,000 historical violations; 60-second runs with real loopback HTTP, RabbitMQ confirmations and PostgreSQL consumer transactions. Camera/violation/alert reads ran at six requests/second, with synchronized worker heartbeat/lease polls every 30 seconds.
- Initial steady load: 600/600 timed events at ten/second persisted; assignment p95 605 ms. Its warmup covered all cameras, so timed alerts were cooldown-deduplicated.
- Fresh-alert burst before optimization: 1,200/1,200 events at twenty/second persisted, 900 new timed alerts; assignment p95 **1,193 ms**, failing the unchanged 750 ms gate. This failed result is retained.
- Identical burst after optimization: 1,200/1,200 timed events persisted, 900 new alerts and 3,000 total outbox rows (including warmup), assignment p95 **644 ms**; alerts/violations/cameras read p95 **78/18/157 ms**; publish-to-handler-completion p95 **54 ms**. All configured gates passed, with zero final backlog. No provider deliveries ran.
- Both burst runs reached **30 checked-out API-process connections**, the current pool ceiling. This is not demonstrated spare capacity. Budget all API replica pools plus migrations/operations below the database limit and repeat realistic burst/retention-sized tests before scaling.
- Runtime: Python 3.12.14, x86_64, five visible logical CPUs with a four-CPU cgroup quota, 32 GiB cgroup memory limit. The load generator and API share one process; metrics are not whole-stack resource sizing. Full reports, package versions, source hashes, limitations and before/after gates are retained in [P6_CONTROL_PLANE_2026-10-16.json](evidence/P6_CONTROL_PLANE_2026-10-16.json).

P6 verification: real Prometheus file discovery passed target addition/removal and coverage checks; the actual worker identity metric was fetched over HTTP. Final full regressions: **193 backend tests passed**, two optional checks skipped (synthetic live video and isolated notification-broker test); **173 AI tests passed**, two optional checks skipped (native RTSP and real CPU-model startup). Real Prometheus discovery ran in the backend suite; actual RabbitMQ and trial ONNX checks ran in the AI suite. The CI-sized isolated workload smoke also passed. Existing backend dependency deprecation warnings remain; GitHub Actions results must be checked separately. Prometheus config/rule checks, production Compose validation, lint and load-script syntax checks pass. External k6 load against a production-like deployment, real factory inventories, scheduled audit/operations notification wiring, host/GPU/database/broker exporters and sustained site load remain pending.

Remaining external work: P7 deployment acceptance—choose pilot hardware/model, enroll the real fleet inventory, validate coverage, independent site accuracy, 24-hour soak, restore/failure drills and measured 10–20 → 50–100 → 200-camera stages. P4 target-GPU acceptance and P5 real-site RTO gates remain open. Do not infer a video-stream capacity or uninterrupted monitoring guarantee from synthetic control-plane tests.


P7 preparation implemented on 2026-10-18. The owner explicitly confirmed that hardware and factory access are not ready. [FACTORY_PILOT_ACCEPTANCE.md](FACTORY_PILOT_ACCEPTANCE.md) now defines commissioning, frozen site acceptance targets, twelve evidence gates, controlled worker/GPU/API/broker/storage drills, isolated backup/restore, stop/rollback criteria and the 10–20 → 50–100 → 200-camera progression.

`infra/pilot/acceptance.py` checks private bundles against a pre-agreed hashed contract, pinned release/model/image/hardware/configuration inventories, site/camera scope, timestamp freshness, preserved attachments, explicit numeric targets and reviewer attestations. It inspects original CUDA-readiness and fleet-coverage reports and requires signed prior-stage decision evidence for expansion. Incomplete, changed, stale or failed evidence blocks review. Success means `ready_for_site_review`, never production approval; hashes and reviewer declarations are not independent proof of site measurements. The checked-in templates intentionally contain no pilot measurements. CI includes the new checker and its regression suite.

P7 local validation: **85 targeted acceptance/sizing-policy tests passed**, covering complete synthetic bundles through the CLI, missing gates, failed accuracy/latency/loss/recovery limits, missing/changed inventories, wrong CPU/model reports, stale coverage, invalid timestamps/values, unsafe attachment paths and output preservation. These are tooling fixtures, not factory evidence. Configured backend/tooling lint, shell syntax, workflow parsing, documentation links and whitespace checks passed. No app runtime, migration, deployment or destructive recovery changed. The backup script comment was corrected: confirmed broker messages not yet consumed cannot be reconstructed from PostgreSQL automatically. Existing readiness/validation docs were aligned with the P4 CUDA fail-closed behavior and P5 schema 0020.

Next handoff: obtain an authorized factory pilot, candidate CUDA hardware/standby, reviewed production model and independent labels; fill and approve the contract before collecting evidence. Real GPU/DVR compatibility, accuracy, provider delivery, sustained load, 24-hour soak, shared-service recovery and site RTO/RPO remain unrun. P7 is **prepared, not accepted**. GitHub Actions results must be checked separately.

Laptop follow-up on 2026-10-18: the owner supplied `nvidia-smi` output for an NVIDIA RTX 2000 Ada Generation Laptop GPU, 8,188 MiB VRAM, driver 595.95. This identifies a local test candidate; it is not target-factory hardware acceptance. Added `check-gpu-windows.cmd` and [WINDOWS_GPU.md](WINDOWS_GPU.md): a separate `.venv-gpu`, pinned official CUDA PyTorch wheel, bounded child process, actual synchronized matrix computation/result verification and preserved JSON reports. No model or camera is loaded and no camera budget is inferred. Production PPE weights and factory access are still missing; the earlier webcam trial remains CPU ONNX and unchanged.

GPU-tool validation: 20 targeted GPU-check/webcam regression tests passed; lint, workflow parsing and whitespace checks passed. A real CPU-only PyTorch subprocess correctly exited 2 with `cuda_unavailable`, proving there is no false CPU fallback success. The official Windows CPython 3.11 CUDA wheel was found in the PyTorch index. The Windows batch launcher and actual laptop CUDA computation have not run in this Linux workspace; Windows Python regressions are included in CI, whose result remains separate. Next action is for the owner to run the launcher locally and supply its JSON report before model/device acceptance.
