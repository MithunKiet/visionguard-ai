# Detection gaps and current health

The dashboard now shows current detection availability and links to **Detection
health**, a scoped, paginated camera view. An activated camera, worker heartbeat
or connected browser socket does not establish that AI is processing frames.

## Evidence and expiry

An upgraded worker records a local monotonic timestamp only after inference on
a fresh frame passes ownership, stream-generation and policy checks and the PPE
validator completes. It clears that evidence on stream changes, activation or
policy changes, and inference timeout/error. Evidence older than 30 seconds is
reported as absent. This describes successful local processing, not detection
accuracy, camera-origin frame age or successful alert delivery.

The existing `/workers/{worker_id}/config-applied` batch now optionally includes
`detection_health: {"inference_age_seconds": 0.5}` or a null age when no recent
inference is known. Health samples use the same tenant, zone, version, process
session and current unexpired camera-lease checks as policy acknowledgements.
Old owners cannot refresh the new owner's health. Samples remain bounded to
200 cameras per request, with the existing HTTP/pass timeouts. Non-finite,
negative, boolean, string and greater-than-30-second ages are rejected.

Migration **0023** adds the latest report and estimated inference timestamps to
`config.camera_applications`. Updates remain a single bulk upsert. Database and
ownership-lock waits are charged against sample age; they cannot make an old
sample look new. Estimated inference time is based on server time minus the
reported local age and handler/database wait. Transit before handler entry is
not independently measured. Workers are trusted reporters; this is not
cryptographic proof of frame processing.

Policy acknowledgements without health data never refresh health timestamps.
Changing the version, zone or ownership clears prior evidence unless a fresh
health sample accompanies the new policy acknowledgement. Reports are retried
on ordinary assignment reconciliation and after hot updates. Fresh inference
can therefore take a nominal 30-second reconciliation cycle plus request time
to appear; this is not a measured recovery SLA.

## API and states

`GET /api/v1/analytics/detection-health` returns the caller's factory/zone-scoped
summary and camera details. It supports `page`, `page_size` (20 default, 100
maximum), `problems_only`, and optional `zone_id`. Scope applies to both counts
and rows. No stream URLs or lease tokens are returned.

| State | Meaning |
| --- | --- |
| `Paused` | Camera disabled or its factory/zone is inactive. |
| `Maintenance` | The camera is in unexpired maintenance mode. |
| `Unassigned` | No worker is assigned. |
| `WorkerUnavailable` | Worker is missing, disabled or lacks an online heartbeat newer than 60 seconds. |
| `LeaseExpired` | Current ownership is missing, inconsistent or expired. |
| `ConfigPending` | The worker has not confirmed the current zone policy under current ownership. |
| `TelemetryMissing` | No inference-health report arrived within 60 seconds. |
| `StreamOffline` | No recent inference is known and the last stream event says offline. |
| `InferenceStale` | Health reporting works but no successful inference is known within 60 seconds. |
| `Detecting` | Recent inference evidence exists and all preceding checks pass. |

Paused and maintenance cameras are counted explicitly and excluded from the
expected monitoring count. Unassigned and unhealthy cameras remain expected
and count as gaps. Zero expected cameras yields `NoMonitoringExpected`, never a
healthy fleet claim. Successful fresh inference can recover a camera even if a
delayed broker stream-status event still says offline. Historical stream events
and `last_seen_at` are not used as inference proof.

The UI polls every ten seconds and expires cached snapshots after 15 seconds,
charging request transit against that browser lifetime. Failed/stalled reads
hide old camera rows and current-detection claims. Reconnect and camera status
events invalidate health queries. Workers, database or broker outages need not
emit a final offline event for evidence to expire. Dashboard alert/violation
read failures are also shown as unavailable instead of empty history.

## Analytics compatibility

The former safety score started at 100 when there were no alerts. The system
does not maintain a historical monitoring-coverage timeline or a validated
safety-score model. `/analytics/safety-score` therefore now returns:

```json
{
  "score": null,
  "status": "Unavailable",
  "reason": "historical_monitoring_coverage_not_measured",
  "alerts_by_severity": {}
}
```

The existing period fields and observed severity counts remain. Even a fully
fresh current fleet snapshot cannot establish coverage over a historical range.
Do not convert null into 0, 100 or a safe label. Compliance percentages also
return null when their denominator is zero; resolved/total counts remain usable.
API clients must handle these nullable values. Recorded zero violations means
zero records, not proof that a site was safe or continuously observed.

This change stores current evidence only. It does not backfill historical uptime
or invent outage durations. Durable coverage intervals, historical camera
inventory/maintenance schedules and a validated scoring method remain future
work. External operations paging is also separate from these in-app warnings.

## Upgrade and acceptance

Back up the database, run `cd backend && alembic upgrade head`, then deploy the
backend, AI workers and frontend. Startup/readiness require schema **0023**.
No new secrets or runtime packages are required. Old workers remain compatible
with policy acknowledgement but show missing detection telemetry until upgraded.

For an authorized pilot, check normal inference, block a camera stream, stop a
worker, interrupt backend connectivity, restore access and verify the dashboard
and scoped details recover. Check an intentional pause and maintenance expiry.
Retain the existing ownership/failover and real-camera model acceptance gates.
Local tests use deterministic frame results and real PostgreSQL; they do not
prove factory camera throughput, image freshness at the source or PPE accuracy.

Downgrade only after stopping upgraded backend writers. Removing migration 0023
drops current health evidence, leaving the earlier policy acknowledgement
contract intact. Prefer forward fixes during operation.
