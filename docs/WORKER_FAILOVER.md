# Safe automatic worker failover

P5 adds process-bound camera leases in migration **0020**. A ready, explicitly configured worker polls every 30 seconds and can take over expired leased cameras in its own factory, within its administrator-set measured camera limit. Heartbeats report health; they do not renew camera ownership. Keep a warmed, authenticated standby running with spare measured capacity at each factory.

## Ownership protocol

- `GET /api/v1/workers/{worker_id}/cameras` requires a UUID `X-Worker-Session` header generated once per worker process. Existing tenant/worker credential checks still apply. A competing process using the same business ID receives HTTP 409 while the first process has live camera leases.
- PostgreSQL serializes admission, policy changes and lease acquisition with the existing enterprise lock. Camera row locks serialize ownership transitions with consumer side effects. The database clock is read after locks, not at transaction start.
- Each camera grant has a random token, increasing generation, process session, database start/expiry and a 90-second TTL. Renewal before expiry preserves the generation. Expiry, restart or takeover creates a new token/generation. Historical grants remain stored for delayed incident replay; renewals update one row rather than creating a new row every poll.
- The worker subtracts the entire request duration and a five-second stop margin from its local deadline. Linux uses `CLOCK_BOOTTIME`, which advances through suspend. Host wall-clock changes cannot extend authorization. Do not change the lease duration or stop margin independently on backend and workers.
- Camera pipelines stop independently of assignment polling or slow inference. Capture children enforce the deadline with their own watchdog, including during blocked open/read/release operations. A generation change reaps the old pipeline before starting another and resets temporal detection state.
- Saved assignments can only continue in the **same process**, before their original lease deadline. The older `EDGE_ASSIGNMENT_CACHE_SECONDS` limit cannot extend a lease. After restart, the journal can replay immediately, but cameras require a fresh API grant; a replacement session waits for any still-live old lease to expire.
- An expired camera transfers only to an eligible polling worker in the same tenant/factory with room in its configured budget. Inactive assigned cameras still count because their readers stay connected. Overflow waits. No cross-factory borrowing, forced early takeover, or automatic failback occurs.
- Legacy generation-zero assignments are never stolen automatically. Stop the old deployment before first lease enrollment. A camera whose owner fails before its first successful lease needs operator reconciliation during that maintenance window.

The HTTP response includes lease credentials and RTSP URLs: protect it like worker credentials and never log the complete payload.

## Events and replay

The worker attaches the original camera token, generation, session and an observation/acceptance time derived from the database time plus elapsed local lease-clock time. The actual camera decode timestamp remains separate and unchanged. The backend checks ownership inside the transaction that persists violations, alerts, occupancy or camera status.

Current occupancy/status messages require the current unexpired generation and owner. Late telemetry from an old owner is rejected. PPE, low-confidence, overcrowding and camera-spec incidents may replay after failover only when their original grant matches that camera/worker/session and their recorded authorization time falls inside the grant's valid interval. The existing event receipt makes replay of the same ID idempotent. Missing tokens, unknown generations and post-expiry observations are rejected to the consumer dead-letter path. Never rewrite saved events to the new owner's token.

These checks trust the deployed worker to report its observations honestly. They do not cryptographically prove camera exposure time or stop an operator with worker credentials from fabricating/backdating observations. Renewals and events require an authoritative PostgreSQL primary; an unsafe database rollback or split-brain database can invalidate fencing assumptions. Keep lease history with the normal database backup and do not prune it while journals/queues may still replay its incidents.

A new owner starts new tracking/cooldowns. A continuing physical violation can therefore produce a new incident ID; event-ID deduplication is not cross-worker person tracking. Disk loss still loses incidents not handed off from that disk. A standby does not automatically copy another worker's journal.

## Availability and limits

With a reachable API/database and a ready standby, the scheduling component of recovery is up to the remaining **90-second lease plus the next 30-second poll**, then HTTP/lock delay, RTSP connection and the required consecutive inference frames. This is a configured timing budget, not a measured site RTO or guaranteed upper bound under overload. Measure failure-to-first-valid-detection and failure-to-alert separately.

An API/database partition causes all affected workers to stop after their remaining lease budget, even if cameras and RabbitMQ are reachable. Extending offline detection past expiry would invalidate safe takeover. Plan factory connectivity/backend availability accordingly. Without spare local measured capacity, cameras remain with expired ownership until capacity is available.

The application fences logical ownership and accepted side effects. It cannot guarantee that an old RTSP TCP socket disappears before takeover during an arbitrarily paused host, kernel failure or hardware fault. The child watchdog handles ordinary process/event-loop/native-read stalls; strict physical connection exclusivity requires camera/gateway/network or infrastructure fencing. Validate bounded host/DB clock behavior and suspension/recovery on production hardware. Do not advertise zero missed detections or uninterrupted monitoring.

## Coordinated deployment and rollback

1. Reserve measured standby capacity for the largest worker failure at each factory. Verify its model/GPU readiness, stream access, worker-specific credentials and configured factory/limit. Capacity values are operator measurements, not automatic hardware sizing.
2. Stop camera ingestion on the old deployment in a maintenance window. Drain accepted legacy events and evidence, including RabbitMQ consumer backlog/dead letters; preserve worker volumes. Stop/fence all old worker and capture processes, including disconnected hosts. Old cached assignments must not overlap the first lease deployment.
3. Stop old backend consumers/API replicas, back up the database, run `cd backend && alembic upgrade head`, and deploy all backend replicas at this version. Readiness requires schema 0020. Start the upgraded workers with their original state volumes. No new environment secrets are required.
4. Verify every camera has a nonzero generation, the expected owner/factory, and a future lease expiry. Confirm the standby has unused measured capacity and all workers are scraped. Do not use ad hoc assignment GET requests with a different process session to inspect a running worker; they are acquisition requests.
5. Exercise the failure drill below before enabling broader production alerting. Check camera processing, edge backlogs, dead letters, alert delivery and duplicate-process HTTP 409s.
6. Rollback is also coordinated: stop/fence every lease worker/capture, drain or preserve journals and queues, stop backend replicas, and restore compatible code/schema (`alembic downgrade 0019`) only inside that maintenance window. Downgrade deletes lease history; retain a backup if any token-bearing incidents remain. Never mix legacy and leased workers on the same cameras or restore a pre-failover database while workers still run.

## Failure drill and monitoring

On an authorized pilot camera, record last accepted inference/alert and current generation. Kill the owner; verify one same-factory standby acquires generation +1 and spare capacity is not exceeded. Restart the old owner and confirm it cannot steal the live lease. Repeat with two competing standbys, a duplicated worker ID on separate volumes, API-only partition, delayed broker delivery, slow/hung capture, and host suspend/resume. Verify expiry stops the old process's inference and fresh post-expiry events cannot modify backend state. Deliver a previously journaled valid incident twice after takeover and check one persisted incident/alert with its original timestamp/evidence key. Record gaps and recovery latency under representative load.

Monitor `vg_camera_lease_remaining_seconds`, `vg_camera_lease_expirations_total`, the supplied `VisionGuardCameraLeaseExpired` warning, `camera.ownership_transferred` logs, consumer dead letters and existing worker/frame/backlog alerts. The expiration warning asks operators to confirm recovery; it does not itself prove a camera is still down. Include all worker targets and configure/test operations notification delivery.

Local tests cover real PostgreSQL races, session conflicts, locality/capacity, expiry, transaction locking, fenced replay, and real spawned capture children with blocked I/O. They do not establish target-GPU capacity, real factory recovery times, database failover safety, or physical RTSP exclusivity under arbitrary host failures. Those remain deployment acceptance gates.
