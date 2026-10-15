# Durable edge incidents

P2 adds a local SQLite journal to each Linux AI worker. It protects **accepted incidents** during broker/object-storage outages and worker process restarts when the worker's persistent disk survives. DVR/NVR recording remains separate. No database migration is added; backend schema head remains `0019`.

## Acceptance and delivery

1. A confirmed PPE detection receives an event UUID, observation timestamp (local decode time with P3) and deterministic snapshot key. JPEG bytes and event metadata commit together locally before the detector acknowledges its cooldown.
2. Separate background loops publish the event to RabbitMQ and upload its JPEG to MinIO. Neither waits for the other. Each retries failures indefinitely with backoff capped at 60 seconds.
3. Events use persistent messages, publisher confirmations and mandatory routing. An unroutable message stays pending. An uncertain acknowledgement can cause replay with the same event ID and timestamp; the backend's existing transactional receipt deduplication prevents duplicate processing of that ID.
4. The local row is removed only after broker confirmation and successful evidence upload. Metadata-only events need only broker confirmation. If JPEG encoding fails, the incident is still accepted without a snapshot.

Broker confirmation establishes broker handoff, **not successful backend consumption or notification delivery**. Monitor backend dead letters and the notification outbox, and retain broker durability/recovery procedures. A reserved snapshot key does not prove the image has uploaded: an incident can appear before its evidence, and the current review UI may need refreshing after upload succeeds. There is no new evidence delivery-status API in this change.

PPE violations, low-confidence violations, overcrowding and camera-spec mismatch use the journal. Occupancy samples, camera online/offline status and worker heartbeat events remain best effort: a coalesced in-memory buffer has at most 2,048 keys and expires entries after 60 seconds. They cannot exhaust the incident journal or replay old camera state after restart.

Original timestamps survive replay, but backend policy is evaluated when consuming the event. Deduplication covers replay of the same saved event; detector tracking/cooldown state is not persisted, so a fresh observation after restart can produce a new incident ID.

## Storage and configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `EDGE_STATE_DIR` | `state`; `/app/state` in Compose | SQLite journal, assignment cache and process lock |
| `EDGE_MAX_EVENTS` | `10000` | Maximum retained rows, including events waiting only for evidence |
| `EDGE_MAX_BYTES` | `536870912` (512 MiB) | Payload/JPEG budget and SQLite page-count ceiling |
| `EDGE_MIN_FREE_BYTES` | `67108864` (64 MiB) | Free-space reserve checked before accepting an event |
| `EDGE_ASSIGNMENT_CACHE_SECONDS` | `300` | Cached assignment age limit; `0` disables fallback, maximum `3600` |
| `EDGE_NETWORK_TIMEOUT_SECONDS` | `10` | Broker operation and object-store socket read timeout |
| `MINIO_SECURE` | `false` | Enable for an HTTPS MinIO endpoint |

Choose storage from measured incident bursts and JPEG size, not camera count alone: `incident rate × outage duration × average retained event bytes`, plus database/cache overhead, rollback-journal space and free-space reserve. SQLite metadata shares the database budget. The database ceiling is not a ceiling on total transient filesystem usage; provision extra disk and monitor host free space. Database pages can remain allocated after replay drains, for reuse.

At a row/byte/disk limit or a failed local write, the worker rejects the new incident explicitly, increments `vg_edge_rejected_total`, and does not acknowledge its detection cooldown. Previously accepted incidents are never evicted to make room. A short-lived event can still be missed while storage is full or the worker is unavailable; this is bounded buffering, not unlimited loss prevention. Fix the cause promptly and verify draining rather than deleting the journal.

The state directory is mode `0700`, with the database and owner lock mode `0600`. Cached RTSP credentials and evidence are plaintext on this local volume; protect the host and use encrypted storage where required. Do not commit, include in image build contexts, or distribute the state directory. Its process lock prevents two processes opening the same volume, but does not fence duplicate worker identities on separate machines.

## Offline startup and authorization

After a successful registration and assignment fetch, the worker saves the validated camera/configuration snapshot. A later transport error, HTTP 429 or HTTP 5xx can use that snapshot while it is fresh, including after process restart. Startup of event delivery and the configuration subscriber does not require RabbitMQ to be reachable. Model files and camera connectivity must still be available locally.

The cache is bound to worker/enterprise identity and a fingerprint of backend URL and worker credential. A credential change, expiry, backward-clock anomaly, invalid response, nonretryable HTTP rejection or authoritative empty assignment cannot grant old camera access. Observed same-enterprise configuration pushes invalidate the cached HTTP snapshot; a concurrent HTTP fetch cannot restore the invalidated snapshot.

Remote revocation cannot be discovered during a partition. Expiry is checked at reconciliation, normally every 30 seconds plus network request time, so stream shutdown can lag the configured age limit. Set the cache duration to the permitted authorization window, or `0` where offline fallback is unacceptable. This does not implement indefinite offline autonomy, distributed leases or automatic failover.

## Upgrade, restart and recovery

1. Keep the P1 factory/camera-budget configuration and schema `0019`. Rebuild worker images; production code is baked into the image.
2. Preserve a distinct persistent volume for each identity. Compose mounts `worker_1_state` and `worker_2_state` at `/app/state`, alongside read-only model mounts in production. Keep the Compose project name stable so it reuses the existing named volumes. Run `python infra/check_production_config.py` to check the supplied topology.
3. Recreate workers with those mounts. On first installation there is no cache until an authorized assignment fetch succeeds. Verify factory assignments, model readiness, stream processing and journal metrics.
4. Restarting the same worker with its original state volume resumes pending delivery automatically. Do not use `docker compose down -v` or remove state volumes while they contain pending incidents. Losing a host disk loses incidents not yet handed off elsewhere.
5. For controlled recovery on another host, stop/fence the original worker first, copy its stopped state directory consistently, and retain its worker/enterprise identity and credentials. The journal refuses a different owner. Test recovery and broker/object-store access before admitting more cameras. A second process with an independent disk is not protected by this local lock.

Before rolling back to code that does not read this journal, drain both channels or retain the stopped state volume for later replay with compatible code. The existing PostgreSQL/MinIO backup script does not back up worker journals or broker queues; include these in the deployment recovery plan and test the chosen RPO/RTO.

## Monitoring and validation

Track `vg_edge_pending{channel="event"|"evidence"}`, `vg_edge_pending_bytes`, `vg_edge_oldest_age_seconds`, `vg_edge_rejected_total`, `vg_edge_delivery_failures_total{channel=...}` and `vg_edge_assignment_cache_active`. Supplied Prometheus rules detect rejected incidents, a backlog older than five minutes, and sustained cache use. Add every worker as a scrape target. Alertmanager delivery is not configured by this repository; connect and test operations notifications.

Local verification on 2026-10-15:

- 112 AI tests passed, including process crash/restart, storage limits, independent broker/evidence retries, failed-write cooldown behavior, cached startup, authorization rejection and cache races. Optional real RabbitMQ tests exercised stable message IDs, confirmations and unroutable publication; the pinned webcam ONNX smoke also ran.
- 48 selected backend integration tests passed against PostgreSQL, including duplicate replay after local journal restart producing one violation and one alert while retaining the original timestamp and snapshot key. Existing notification delivery regressions also passed.
- Lint, production Compose validation and Prometheus rule evaluation passed.

Object-store failures were simulated in the retry tests; there was no real GPU/DVR/site outage drill or 200-camera measurement. Native upload calls use socket timeouts, not an absolute thread termination deadline. P3 now provides [capture isolation and local decode-age checks](CAPTURE_ISOLATION.md); upstream camera/DVR freshness still needs site validation. P4–P7 remain tracked in [the remediation plan](MULTI_FACTORY_REMEDIATION.md).
