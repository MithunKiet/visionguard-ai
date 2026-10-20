# P7: factory pilot acceptance

**Status: tooling prepared; site acceptance has not run.** On 2026-10-18 the owner confirmed that hardware and factory access are not ready. No camera-per-GPU limit or production approval follows from this document. Existing DVR/NVR equipment retains recordings; VisionGuard processes authorized live feeds and incident evidence. Audio is not required.

## What must be available

Name a site owner, safety/label reviewer and operations responder. Obtain authorized access to one factory, initially 2–4 commissioning cameras and then 10–20 representative pilot cameras. Identify a candidate CUDA server and equivalent standby, network routes, reviewed nine-class model weights/license, independent site labels, a pilot tenant, private storage and an authorized notification test destination. Keep RTSP credentials in secure environment settings, never in a bundle, shell argument or Git.

Choose candidate hardware using [PRODUCTION_CAPACITY.md](PRODUCTION_CAPACITY.md); rental/loan equipment is sufficient for comparison. Record CPU, RAM, GPU/VRAM, driver/CUDA, disk, network, model and camera profiles. No fixed hardware shopping list is justified by the current evidence. Plan factory-local ingest; measure central API/broker/database/storage traffic and outages. The supplied Compose stack is single-host infrastructure, not multi-site HA.

## Freeze the experiment before collecting acceptance results

Copy the two templates from the repository root into private ignored storage:

```sh
mkdir -p capacity-data/site-a/evidence
cp infra/pilot/contract.example.json capacity-data/site-a/contract.json
cp infra/pilot/bundle.example.json capacity-data/site-a/bundle.json
```

On Windows, create these folders and copy the files in Explorer; the checker itself works with Python 3.11+. Do not submit the empty templates as evidence. Their nulls intentionally fail.

Fill `contract.json` with actual enterprise/factory UUIDs, unique camera UUIDs, named owners, UTC timestamps with offsets, supported PPE classes and site conditions. `required_ppe` accepts helmet, vest, gloves and safety_shoes. Define conditions covering shifts, distance/pixel size, lighting, occlusion, motion and scene density. Unsupported PPE, violence detection and identifying named employees are outside the current model contract.

Pin these values under `release`:

| Field | Required identity |
| --- | --- |
| `git_commit` | Full 40-character deployed commit |
| `model_sha256` | Reviewed production checkpoint SHA-256, not the webcam demo model |
| `images_sha256` | SHA-256 of a retained inventory of immutable image digests and runtime packages |
| `hardware_sha256` | SHA-256 of a retained hardware/driver/GPU/network inventory |
| `configuration_sha256` | SHA-256 of a retained effective, redacted configuration: camera profiles, FPS, thresholds, tracking/voting/cooldown, leases, budgets and notification/media settings |

Reference those inventories under `bundle.release_evidence` using relative paths and SHA-256 values. The checker verifies their bytes against the frozen contract fingerprints as part of the deployment gate. Preserve private source configuration separately; do not export passwords to compute this fingerprint. A model, image, hardware, camera placement or effective detection configuration change requires a new contract and affected measurements. Do not combine favorable measurements from incompatible runs.

The site owner must fill and agree every `policy` target **before** the observation starts:

| Target | Meaning |
| --- | --- |
| `min_event_precision`, `min_event_recall` | Fractions in (0, 1]; minimum across all required PPE/condition cells |
| `max_false_alerts_per_camera_hour` | Maximum rate across those cells, including observed negative periods |
| `min_positive_episodes_per_cell` | Positive integer; independently labeled episodes per cell |
| `min_negative_camera_hours_per_cell` | Positive observed negative hours per cell |
| `max_capture_to_alert_p95_seconds` | Positive source-visible-event to persisted-alert latency limit |
| `max_failover_seconds` | Positive worst acceptable outage-to-valid-processing recovery limit |
| `max_restore_seconds`, `max_rpo_seconds` | Agreed service recovery and maximum data-loss windows |

These targets deliberately have no invented accuracy/recovery defaults. The checker additionally requires at least 24 continuous hours, resource peaks at most 85%, and zero specified losses, inference errors, stale-frame incidents, unauthorized overlap, rejected edge events and unresolved delivery backlog. The 85% limit follows the existing sizing planner; review memory, disk, network and connection headroom separately. Normal latest-slot frame replacement is not a lost incident or stale-frame event.

Record `approved_by` and `approved_at`, retain the approved contract in controlled storage, and hash its exact bytes. For any file, this portable command prints SHA-256 without printing contents:

```sh
python -c "import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())" capacity-data/site-a/contract.json
```

Put this digest in `bundle.contract.sha256` and every gate's `contract_sha256`. Do not reformat the contract afterward. Hash every attached report and set its relative path and digest under `evidence`. Files must remain inside the bundle directory; URLs, absolute paths and traversal/symlink escapes fail. Individual attachments are limited to 32 MiB; attach bounded reports/manifests and keep footage in controlled storage.

## Execute and retain the evidence

Start with commissioning, then start a fresh full-load observation window. Use the same pinned deployment throughout the accepted run. Each gate needs a named reviewer, a substantive summary, an `observed_at` timestamp within the window, all required checks, numeric measurements where present and hashed evidence. Use `pending` or `fail` honestly. Fill measurements from retained source data, not estimates. The checker validates submitted evidence consistency; it cannot watch cameras or verify reviewer identity.

| Gate | Procedure and required evidence |
| --- | --- |
| deployment | Verify camera/worker inventory, licenses, runtime production settings, secrets and image scans. Run `python infra/check_production_config.py` as a topology check; also inspect actual deployment settings. Retain inventories matching the contract fingerprints. |
| model | Run the [P4 preflight](MODEL_READINESS.md) in the target image/GPU allocation for every worker hardware profile. The **first attachment** must be its original JSON: `model_ready`, actual `cuda:0`, GPU available, matching model digest and run timestamp. Attach remaining worker reports and verify equivalent allocations. |
| accuracy | Use the [runtime nine-class held-out evaluator](REAL_CAMERA_VALIDATION.md), then evaluate contiguous event episodes through tracking/voting/cooldown. Keep raw labels, session split, TP/FP/FN, missed episodes, false alerts, sample counts, negative hours and uncertainty per PPE/condition cell. Enter worst precision/recall/sample support and highest false-alert rate, never an average hiding a failing cell. Undefined/unobserved classes cannot pass. The webcam six-class report and box-only scores cannot establish event accuracy. |
| camera_dvr | Probe each authorized camera, verify primary/substream connection limits, NVR playback during/after parallel AI ingest, timestamp/visible-clock freshness, placement and PPE pixel sizes. Test reconnects. Record actual resolution/codec/bitrate/sample FPS and supported observation areas. Do not infer one universal distance. |
| capacity | Run the integrated workload at the full stage camera count with expected viewers/reviewers and alert bursts. Measure each camera's achieved FPS and capture-to-alert latency, all capture children, whole-device GPU memory, host CPU/RAM/network/disk, shared-service limits and database connections. Every camera must meet >=95% of target FPS. Use the [existing sizing planner](PRODUCTION_CAPACITY.md) per worker/profile with headroom and tested spare capacity; attach its inputs/results. Synthetic metadata or inference-only throughput is insufficient. |
| soak | Observe at least 24 uninterrupted hours at full stage load, including representative shifts. Retain telemetry with gaps identified, event reconciliation, failures, memory/disk growth and queue/outbox trends. A wall-clock interval without continuous observations is insufficient. Enter all zero-loss/error counts explicitly. Restart an interrupted soak. |
| failover | Execute the controlled drills below. Record worst recovery, camera grant/generation history, old/new worker observations and capacity during takeover. Verify no overlapping authorized owners. |
| delivery | In the isolated pilot, interrupt broker and object storage separately; generate uniquely identifiable safe test incidents, restart the worker and reconcile journal, broker, database receipts, alerts, evidence objects and provider receipt IDs after recovery. Record configured cooldown/suppression effects separately. Zero backlog requires explicit drain verification. |
| monitoring | Generate inventory/file discovery and run the [P6 coverage audit](FLEET_MONITORING.md). The **first attachment** must be the original successful audit JSON from the final hour of the observation; counts must agree. Attach the inventory and reviewer scope reconciliation. Schedule the audit and route failures. Demonstrate an actual page to the authorized test destination and acknowledge it; Prometheus rules alone do not deliver pages. Include host/GPU/disk/broker/outbox monitoring. |
| restore | Complete the isolated recovery procedure below. Retain backup timestamps/checksums, restore logs, schema, row/event/object reconciliation and measured RPO/RTO. Verify offsite retrieval and worker-state recovery. |
| security | Test actual HTTPS certificates, restricted infrastructure/RTSP egress, scoped worker keys, cross-tenant/role denial, session expiry/logout and unauthorized HLS/segment/evidence access. Test authenticated playback/review and incident state changes on the actual deployment. |
| rollback | Rehearse rollback while preserving data and worker journals. Name responders, escalation paths, stop thresholds and known defects; no unresolved blocking defect may remain. Attach the site decision and any retest obligations. |

Model and monitoring JSON get additional machine checks. All other checks are explicit reviewer attestations with attached evidence; the checker does not calculate accuracy from labels, query cameras, continuously collect telemetry, execute failure drills or verify backup contents. Hashes detect changed attachments; they are not signatures or independent attestation. A synthetic fixture could satisfy the structure, so a human must inspect provenance and observations.

## Controlled failure drills

Run during an agreed isolated pilot window with a site responder present; these are manual site operations, not commands executed by the acceptance checker. Keep the DVR recording and retain the normal safety process throughout the pilot.

1. Establish steady processing and note camera leases, generations and incident IDs. Confirm same-factory standby capacity under the actual load.
2. Stop one worker; measure from last valid result to first valid result from its successor. Verify takeover only after the 90-second lease expires and measure scheduling/reconnect overhead. Repeat for a native GPU hang under the external supervisor. Do not claim instant failover.
3. Partition the worker from the API/database authority. Verify camera capture/detection stops by local authorization expiry (five-second safety margin, request time deducted); cached assignments cannot extend authorization. Reconnect and confirm current generation/session only. Repeat authoritative service restart/recovery in the isolated deployment.
4. Disconnect one camera while keeping the others active. Confirm outage status, healthy-camera progress, bounded memory and fresh results after reconnect; check the DVR connection budget too.
5. Interrupt broker and storage independently and together for the planned bounded outage. Track event IDs through recovery/restart and verify stored evidence and actual provider receipts. Never interpret an unavailable camera as compliant.

Use [WORKER_FAILOVER.md](WORKER_FAILOVER.md) and [DURABLE_EDGE_EVENTS.md](DURABLE_EDGE_EVENTS.md) for exact guarantees. Broker confirmation is not backend consumption; a lost confirmed broker queue can lose an event absent a separately demonstrated durability/recovery strategy. A paused/kernel-stuck old host can retain a physical RTSP connection beyond application fencing; exercise network/host fencing where physical exclusivity is required. A worker standby does not recover failed PostgreSQL, broker, storage or ingress.

## Isolated backup and restore drill

Use the verified bundle and isolated `infra/backup/restore.sh` workflow in [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md). It creates new databases/buckets and never starts application services. Provision separate isolated PostgreSQL and object-store destinations, prevent notification delivery and worker/camera connections, and have the responder verify those destinations before running the drill.

1. Seed the pilot with known event/alert/evidence references. Record a reconciliation manifest, backup cutoff and authoritative timestamps. Quiesce relevant writes or document a tested cross-store consistency boundary; independent database and object copies are not an atomic snapshot.
2. Retrieve the encrypted offsite copy into controlled storage and verify file checksums. The current tool verifies a shared PostgreSQL snapshot and referenced objects; it does not implement offsite encryption/retrieval, distributed atomic snapshots, broker backup or edge-state backup. Scheduling examples are not automatically enabled.
3. Restore PostgreSQL into an empty disposable target using error-stopping restore options, then restore evidence objects. Record tool exit codes, schema migration head (currently 0025), table counts, relationships, receipt identities, referenced object existence/checksums and authorized report/evidence access.
4. Recover a separate copy of the worker persistent journal in an isolated test deployment. Verify replay with original event IDs and ownership history, without re-authorizing old camera capture. Account separately for confirmed-but-unconsumed broker events and unconfirmed local incidents.
5. Measure recovery until the isolated service is usable and the actual data-loss window against the backup boundary. Compare with the frozen RTO/RPO, reconcile missing/duplicate events and objects, and retain evidence. Record retention, key recovery, restore ownership and the next rehearsal date.

Stop if destination isolation or reconciliation is uncertain. No destructive restore or host failure has been performed in this cloud task.

## Evaluate and stage the rollout

Run from the repository root after populating the bundle:

```sh
python infra/pilot/acceptance.py \
  --bundle capacity-data/site-a/bundle.json \
  --output capacity-results/site-a-acceptance-001.json
```

Exit **2** / `blocked` means missing, stale, malformed or failed evidence. Exit **0** / `ready_for_site_review` means the submitted checks pass and require human review. `production_approved` and `evidence_independently_verified` always remain false. Existing output files are never overwritten. Reports older than 30 days, future/naive timestamps and changed hashes fail. Use a new output path every run and preserve failed attempts.

| Stage | Simultaneously observed cameras in one factory | Advancement |
| --- | --- | --- |
| Commissioning | 2–4 | Fix wiring/credentials/placement; no full acceptance claim |
| `pilot` | 10–20 | All gates, >=24-hour soak, named site review |
| `expansion` | 50–100 | Fresh full-load bundle plus retained signed pilot decision |
| `factory` | 200 | Fresh full-load bundle plus retained signed expansion decision |

For expansion/factory stages, set `previous_stage_signed_off=true` only after the site decision and attach it under `previous_stage_decision` as a path/SHA-256 reference. The tool checks presence/integrity; the reviewer must verify signature, prior stage, scope and conditions. Do not treat the software report as that decision. Repeat per factory and retest shared services at total fleet load; five passing factories separately are not a simultaneous 1,000-camera test. Nonstandard stage sizes require a reviewed policy/tool change, not counting disconnected cameras.

Stop expansion on a missed gate, unknown camera status, ownership overlap, uncontrolled backlog, storage exhaustion, failed notification/restore or accuracy regression. Preserve evidence, roll back under the rehearsed procedure, fix the cause and rerun the affected gates/full soak. The remaining external action is to provide site access, candidate hardware and reviewed model/data so these measurements can begin.
