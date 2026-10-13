# Reliable alert delivery

Apply migration `0018` with `alembic upgrade head` before starting this version. Container startup already runs migrations. Startup/readiness reject an older schema. The migration adds `notifications.deliveries`; it does not resend historical alerts or change existing alert records.

## Guarantees and limits

Each new alert and its delivery jobs commit in one PostgreSQL transaction. Email, Slack, webhook and live-update delivery run independently after that commit. A failed channel cannot block alert creation or force successful channels to resend. PPE, overcrowding and camera-quality events retain their event IDs in an atomic receipt, so replay does not create another alert or another set of jobs. Camera-quality alerts remain live-update only.

Workers select due jobs with `FOR UPDATE SKIP LOCKED`. A row lock spans one bounded send and its result update. Multiple API replicas can run workers safely; a crashed or cancelled worker releases its lock and its unfinished job becomes eligible again. Successful results and attempt logs commit together. PostgreSQL must use durable storage and have tested backups; the outbox cannot compensate for lost database storage.

Delivery is **at least once**. If a provider accepts a message and the worker crashes before recording success, the next attempt may send it again. Generic webhooks include a stable `Idempotency-Key` header and `delivery_id` field; receivers must store and deduplicate that key. Email retries use a stable `Message-ID`, which does not guarantee mailbox deduplication. Slack incoming webhooks do not provide an exactly-once guarantee. Attempt counts include completed, recorded attempts; an interrupted transaction may have contacted a provider without recording an attempt.

Live updates use a stable event ID. `Published` means Redis accepted the update; it does not prove that a browser was connected or a desktop notification was shown. Offline clients must reload alerts through the persisted alert API. Live violation/occupancy refreshes, continuous recordings and employee identification are outside this delivery guarantee.

Email recipients are deduplicated when jobs are created. Their current active status, email address and camera visibility are checked again at delivery time. Recipient selection is a snapshot of the zone/fallback configuration at alert creation; changing that configuration affects future alerts. Pending jobs for resolved or false-positive alerts are skipped. Providers use current deployment-level credentials; webhook URLs and credentials are not persisted in delivery payloads or failure messages.

## Operator workflow

Enterprise and system administrators can open **Notification delivery** in the dashboard. It shows failed and waiting counts, the oldest waiting notification, paginated job status, attempt count and failure reason. Administrators can retry `Failed` or `Skipped` deliveries. Other tenants cannot list or replay these jobs. A retry queues work; it does not send synchronously, does not replay successful jobs, and records an audit entry in the same transaction.

| Status | Meaning | Action |
| --- | --- | --- |
| Pending | Waiting for an available delivery worker | Monitor queue age |
| Retrying | A recorded attempt failed; a future attempt is scheduled | Check provider/network health |
| Failed | Automatic attempt budget exhausted | Repair the cause, then retry |
| Skipped | Channel was unconfigured, recipient unavailable/out of scope, or alert closed | Inspect the reason before retrying |
| Sent | Email/Slack/webhook provider accepted the send | No automatic resend; no read receipt implied |
| Published | Redis accepted the live update | Check persisted alerts for authoritative state |

Corresponding authenticated API endpoints:

- `GET /api/v1/notifications/deliveries?status=Failed&page=1&page_size=50` (optional `alert_id`).
- `GET /api/v1/notifications/deliveries/summary` returns status counts and `oldest_pending_at`.
- `POST /api/v1/notifications/deliveries/{delivery_id}/retry` queues a failed/skipped job. Retrying another status returns `409`.

Monitor failed counts and oldest-pending age against the site's alert-latency target. Also monitor RabbitMQ's `backend.ai_events` and `dlq.ai_events` queue depths. Readiness checks the delivery worker tasks, but readiness alone does not certify timely delivery or provider availability. Retain delivery/attempt records according to the site's retention policy; automatic archival is not implemented.

## Retry configuration

Set these variables on the backend process (or in `docker-compose.prod.yml` under `backend.environment` when using Compose):

| Variable | Default | Behavior |
| --- | --- | --- |
| `NOTIFY_RETRY_ATTEMPTS` | 3 | Automatic attempt budget, including the first attempt |
| `NOTIFY_WORKERS` | 2 | Concurrent sends per backend replica; keep database pool capacity in mind |
| `NOTIFY_POLL_SECONDS` | 2 | Idle polling interval |
| `NOTIFY_TIMEOUT_SECONDS` | 20 | Total bound on a delivery attempt |
| `NOTIFY_RETRY_BASE_SECONDS` | 30 | Exponential retry base, with 20% jitter |
| `NOTIFY_RETRY_MAX_SECONDS` | 3600 | Maximum automatic retry delay |

Each job stores its attempt budget at creation. Manual replay grants another configured budget while preserving recorded attempt history and delivery identity. An unconfigured channel is visibly `Skipped`, not falsely marked sent. Enabling a channel does not automatically send old skipped jobs; review and replay the desired jobs explicitly. The worker retries HTTP errors within its bounded budget, including rate limits; provider-specific `Retry-After` scheduling is not implemented.

## Broker failure recovery

Transient database connection, pool-exhaustion, serialization and deadlock errors requeue the original broker message after a short pause. Its original event ID is preserved. Invalid events and non-transient processing errors go to the existing durable `dlq.ai_events` queue for investigation instead of looping indefinitely.

After repairing a dead-lettered event's cause, use the broker's controlled replay tooling to republish its original JSON body and routing key to `ai_worker_events`. Preserve `event_id`; do not generate a new one. Confirm that the republished persistent message was accepted before acknowledging/removing the original DLQ entry. Requeueing a DLQ entry into the DLQ itself does not retry application processing. There is no automatic DLQ drain or historical-alert backfill in this change.

## Validation

Cloud validation on 13 October 2026 passed: **62 backend tests**, including the real RabbitMQ redelivery/dead-letter test; **6 Chromium browser tests**; backend lint; and the TypeScript/Vite production build. Migration `0018` passed both an upgrade of the existing disposable test database and a fresh migration chain, followed by a disposable `0018 → 0017 → 0018` round trip. The existing large-frontend-bundle warning remains.

Regression tests cover atomic rollback, duplicate event delivery, per-channel retries, persistent backoff, independent workers, cancellation/recovery, crash after provider acceptance, stable transport identifiers, current recipient permissions, closed-alert suppression, administrator replay and tenant isolation. Transport tests mock SMTP/HTTP; no external recipients are contacted. An optional test using `TEST_RABBITMQ_URL` checks actual message requeue and dead-letter behavior with isolated temporary queues. CI provisions PostgreSQL, Redis and RabbitMQ for these checks.

Before production use, exercise the intended providers, credential rotation, provider rate limits and a realistic alert burst in an approved staging deployment. Size workers and database connections from measured queue age and provider throughput. Rolling back migration `0018` drops delivery history and pending work: drain/export that work first, or roll application code forward instead.
