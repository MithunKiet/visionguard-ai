# Factory-scoped worker scheduling

Each worker must be configured for one factory and an explicit camera budget before receiving streams. Multiple workers may serve the same factory. Camera registration and worker polls assign unowned cameras only to recent online workers in that factory, within the same enterprise and below the configured limit. Other factories' spare capacity is not borrowed.

## Upgrade and configure

This change requires migration **0019**. Schedule a maintenance window: legacy workers start with `factory_id=null` and `max_cameras=0`, and their camera polls return no streams until an administrator configures them. Existing assignment rows are preserved for reconciliation; the migration does not guess factory scope or hardware capacity. Old backend code must not run concurrently with the new scheduler because its assignment writes do not acquire the new scheduling lock.

1. Record current worker identities, factory ownership and assignment counts. Stop old backend instances and workers during the coordinated upgrade. Back up the database and retain the previous application artifact.
2. Run `alembic upgrade head` using the backend environment, then start the updated backend.
3. Sign in as an enterprise or system administrator. List workers with `GET /api/v1/workers` and factories with `GET /api/v1/factories`. If a worker has not registered, start it to register its identity; it will receive no streams before configuration.
4. Configure each worker using its **public UUID** from the list, not its internal database ID or business name:

   ```http
   PUT /api/v1/workers/<worker-public-uuid>/scheduling
   Authorization: Bearer <administrator-access-token>
   Content-Type: application/json
   ```

   ```json
   {
     "factory_id": "<factory-public-uuid>",
     "max_cameras": 4
   }
   ```

   `4` is an example API value, not a measured recommendation. Use a deliberately small pilot budget initially and a measured safe limit for deployment. The accepted range is 1–10,000; this validation range is not a capacity claim. Configuration is currently API-based; no worker-management dashboard was added.

5. Start/restart the updated workers. On their next assignment poll (normally every 30 seconds plus request duration), valid existing assignments resume and pending cameras fill available capacity. Confirm every expected camera is assigned and producing fresh results.

Configuration returns `409 WORKER_POLICY_CONFLICT` if an existing nondeleted assignment belongs to another factory/tenant or the proposed limit is below the assigned count. It does not silently move cameras or truncate an active worker's list. Mixed-factory legacy assignments require an operator-reviewed redistribution with original workers stopped/fenced; automatic live reassignment is intentionally outside this change. Do not clear assignments while their old worker could still be processing them.

Heartbeat payloads cannot set `factory_id` or `max_cameras`; additional fields are rejected. Existing heartbeat fields and credential checks are retained. The worker list and heartbeat responses now include the administrator-configured factory public UUID and camera limit.

## Admission and pending cameras

- A camera with no eligible capacity is created successfully with `worker_id=null`. It remains visible as unassigned through the camera API; it is not currently monitored by an AI worker.
- Polls backfill up to 100 pending cameras per transaction within the configured factory. Further polls process the remaining backlog.
- Eligible workers must be online, active, not deleted, and have a heartbeat newer than 60 seconds. Disabled/deleted factories are excluded.
- Allocation balances assigned-count/camera-limit ratios, with a stable worker-ID tie break. It does not estimate GPU utilization, frame complexity or decode cost.
- Inactive assigned cameras still consume admission slots because the current worker retains their stream connections. Soft-deleted cameras release capacity for later backfill.
- Existing assignments to stale workers are retained. This is pending-camera backfill, **not automatic failure recovery**. Leases/fencing are a separate remediation priority.
- PostgreSQL serializes short admission and policy transactions per enterprise with a `FOR NO KEY UPDATE` lock. Concurrent API replicas cannot spend the same last slot. Camera/config retrieval uses a single joined query instead of per-camera ID/config lookups.
- Assignment payloads enforce worker factory, enterprise, active/deleted state and matching camera parents at read time. Unconfigured or invalid legacy assignments do not expose camera streams.

Changing a budget upward requires new measurements if the model, stream profile, sampling rate or hardware changed. Configuration changes record the administrator and update timestamp; this change does not add an immutable scheduling-history ledger.

## Rollback

Stop the new workers and all backend instances before downgrade. Migration downgrade to `0018` removes factory/capacity policy columns and preserves camera assignments. Running the previous application reintroduces the earlier locality/capacity weaknesses; do not use rollback as an approved multi-factory operating mode. Restore policy configuration after any re-upgrade, as the removed values cannot be recovered automatically.

See [the remediation plan](MULTI_FACTORY_REMEDIATION.md) and [measured sizing workflow](PRODUCTION_CAPACITY.md). Scheduling limits do not validate detection accuracy, offline operation, automatic failover or a 200/1,000-camera deployment.
