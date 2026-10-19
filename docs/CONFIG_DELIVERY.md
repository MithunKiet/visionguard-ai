# Reliable zone configuration delivery

Zone detection policy saves and history restores now commit the new version,
history entry and a delivery record in one PostgreSQL transaction. A broker
failure after a successful save cannot erase the delivery intent. The API
returns the saved configuration; application is reported separately.

## Delivery and recovery

1. An administrator saves through `PUT /api/v1/config/zone/{zone_id}` or restores
   a history entry. Row locking serializes the monotonically increasing version.
2. Each API process runs a configuration dispatcher. PostgreSQL
   `FOR UPDATE SKIP LOCKED` prevents concurrent attempts for the same event.
   Each network attempt has a five-second timeout. Failed attempts retry
   indefinitely with exponential backoff and jitter, capped at five minutes;
   an idle dispatcher polls every two seconds. Failure details store only an
   exception type, never credentials or raw broker responses.
3. The publisher uses persistent messages and publisher confirmations. A stable
   event UUID survives retries. A crash after broker acceptance but before SQL
   commit can redeliver; workers ignore duplicate/older versions.
4. Workers install newer hot-pushed policies and report their installed zone
   and version. Their ordinary assignment reconciliation also repairs missed
   pushes and retries lost reports. The nominal interval is 30 seconds plus
   request/reconciliation time; this is not a measured delivery SLA.
5. Reports carry the process session and camera lease token. The backend locks
   the camera, checks the current owner, unexpired lease, tenant, zone and exact
   current version, then writes confirmations in one batch. Old owners cannot
   mark a new owner's configuration applied. Repeated confirmations refresh
   freshness without changing the first server confirmation time.

Worker reports are bounded to 200 cameras per request, five seconds per HTTP
request and ten seconds total per reporting pass. Failure does not stop
detection; the next reconciliation retries. No token or camera URL is included
in the administrator status response. A late assignment response cannot replace
a newer policy already installed by a push. Moving a camera between zones
recreates its pipeline so equal version numbers from different zones cannot be
confused.

The broker fanout queues remain ephemeral. `Published` means broker acceptance,
including when no worker was subscribed; it does **not** mean worker application.
Missed pushes recover through authoritative HTTP reads, including while the
broker is unavailable. Starting the backend still requires its existing broker,
database, Redis and storage dependencies. This change permits a running API to
save settings without calling the broker; it does not bypass deployment health
checks or infrastructure outages.

## Status and interface

`GET /api/v1/config/zone/{zone_id}/delivery` uses the existing tenant and
factory/zone scope checks. It returns the current version, camera counts, the
last current application confirmation time, and publication attempt/status
metadata. Configuration values and lease tokens are not returned here.

| Application status | Meaning |
| --- | --- |
| `Pending` | At least one enabled, non-deleted camera lacks a fresh confirmation of this zone/version under its current live lease. |
| `Applied` | Every such camera has a matching confirmation received within 90 seconds and a still-valid current lease. |
| `NoActiveCameras` | There are no eligible cameras; this never implies successful application. |

Inactive cameras are excluded. Unassigned cameras remain pending and are counted
separately. New cameras or ownership changes can return a previously applied
zone to pending. A stopped reporting process loses applied status through lease
expiry or confirmation age. Initial/default policies saved before this feature
show publication `ReconciliationOnly`; they can still be confirmed via HTTP.

In **Zones → Edit mandatory PPE**, saving keeps the dialog open. It shows the
saved version, confirmed/pending camera counts, automatic retry status and the
last application time. Status refreshes every five seconds while open without
overwriting unsaved PPE selections. Failed status reads hide cached success;
failed configuration reads disable Save. Reopening the dialog resumes tracking.

`Applied` attests that a trusted worker installed the zone policy in memory.
It does not prove frames are flowing, that a particular frame used the policy,
that the model supports every requested PPE class, or that accuracy is acceptable.
Check camera health and the separate model/site acceptance gates.

This contract covers all fields saved/restored through the zone configuration
API. Per-camera overrides, activation, RTSP connection changes, worker scheduling
and zone metadata use their existing flows; this endpoint is not an application
acknowledgement for those changes.

## Upgrade and operations

1. Back up the database using the established deployment procedure.
2. Run `cd backend && alembic upgrade head` with the deployment's configured
   database. Migration **0021** adds `config.deliveries` and
   `config.camera_applications`; it does not reset policies or camera leases.
3. Deploy the backend, then AI workers and frontend. No new environment secrets
   are required. Existing workers can still reconcile settings but will remain
   unconfirmed until upgraded. Preserve the earlier coordinated lease rollout
   in [WORKER_FAILOVER.md](WORKER_FAILOVER.md) if upgrading from before 0020.
4. Check `/health/ready`: startup and readiness now share the same schema head,
   and readiness checks that the configuration dispatcher is running.
5. On an authorized test zone, save a reversible policy change, check its version
   and pending/application counts, then restore it through history. Check a
   disconnected worker's recovery before relying on the flow at a site.

For persistent `Retrying`, inspect broker connectivity and the safe exception
type. For `Published` with pending cameras, check worker HTTP access, software
version, scheduling, lease validity and worker logs. Saving again is unnecessary
for retry. A newer policy supersedes older versions at application time; older
outbox rows are retained as delivery evidence. No automatic retention deletion
is introduced. Include both tables in database backups and capacity planning.

Prefer forward fixes. A downgrade to 0020 drops delivery and confirmation data:
stop the new dispatchers first and preserve pending records/backups. Do not
downgrade while pending delivery intent is still needed. Lease history remains
subject to the stricter failover rollback rules.

## Local verification

Tests exercise transaction rollback, unavailable publishers, backoff and retry
with a new dispatcher instance, crash/cancellation rollback, concurrent dispatch,
real RabbitMQ confirmation with and without a subscriber, version restore,
scope isolation, identity/session/zone/version rejection, lease replacement and
expiry, confirmation freshness and no-camera behavior. A 100-camera regression
requires the same three SQL statements as a one-camera acknowledgement: locked
ownership read, database clock and bulk upsert.

AI regressions cover monotonic push/HTTP reconciliation, report retry, expired
ownership exclusion, bounded batches and confirmation only after installation.
Browser regressions cover save → retry → publication → application, unavailable
status, unsaved form preservation and load failures. These local checks do not
replace the real factory acceptance tests in [FACTORY_PILOT_ACCEPTANCE.md](FACTORY_PILOT_ACCEPTANCE.md).
