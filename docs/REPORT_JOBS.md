# Background reports

Reports now persist as jobs before generation starts. Enterprise administrators
can use **Reports** in the sidebar to request PDF or Excel exports, follow
progress, retry failed reports and download completed files. Jobs survive page
navigation and API process restarts.

## API contract

| Endpoint | Behavior |
| --- | --- |
| `POST /api/v1/reports/generate` | Returns HTTP **202** and the persisted job immediately. |
| `GET /api/v1/reports?page=1&page_size=20` | Lists jobs with pagination metadata; maximum page size 100. |
| `GET /api/v1/reports/{id}` | Returns current job status, stage, attempts, row count and safe failure details. |
| `POST /api/v1/reports/{id}/retry` | Requeues a failed report with three additional attempt opportunities; returns 202. |
| `GET /api/v1/reports/{id}/download` | Returns a one-hour signed URL only for a completed report; otherwise 409. |

Generation accepts `report_type` (`violations_summary` or `alerts_summary`),
`format` (`pdf` or `xlsx`), and timezone-aware `from_date`/`to_date`. Date ranges
must be ordered and at most 366 days. Boundaries are inclusive. Report data uses
UTC timestamps; the browser converts its local date/time inputs to explicit UTC.

Clients can send a UUID `Idempotency-Key` header. Repeating the same key, actor
and parameters returns the existing job, including after a lost HTTP response.
Reusing a key for different parameters or a different actor returns 409. The
browser retains the key for retries of the unchanged request within the mounted
Reports page. After reloading or changing the form, check history before
requesting another export. Clients that omit the header create a new job on
each accepted request.

Generation formerly returned a completed result synchronously. API consumers
must now handle 202, follow status and request downloads after completion. List
consumers must paginate instead of assuming the first response is all history.
Existing completed reports retain their object keys and download behavior.

## Processing and recovery

Each API process starts one report dispatcher. Admission is serialized per
enterprise and allows at most ten queued/running/retrying jobs per enterprise;
further requests return 429. PostgreSQL `FOR UPDATE SKIP LOCKED` claims a job
without duplicate active claims between replicas. File generation does not
hold the admission or claim locks.

Jobs follow `Queued → Running → Completed`, with visible stages
`Reading → Rendering → Uploading`. These are processing stages, not estimated
percentages. The browser polls every five seconds while the page is open.

Every attempt runs in a separate Python process with a 120-second deadline.
The parent kills and reaps timed-out or cancelled work. The child also has its
own deadline so a crashed parent cannot leave generation running indefinitely.
Progress and completion writes require the current attempt token and an
unexpired 150-second lease. A new process can reclaim an interrupted job after
expiry; stale attempts cannot publish another attempt's result. Each upload
uses a distinct object key, so a late upload cannot overwrite a newer result.

Storage failures, timeouts and interruptions retry automatically, normally after
30 then 60 seconds, up to three total attempts. Oversized results, revoked
requester access and rendering failures fail immediately with an actionable
message. After the limit, an administrator can retry explicitly. Repeating a
retry request while the job is already active does not create another attempt.
The attempt counter is cumulative; a manual retry grants three more attempts.

The requesting account must still be active with enterprise-wide report access
both before extraction and before completion. Revoked requests do not become
downloadable. To replace a request from an unauthorized original account, create
a new report with a currently authorized account. The current download caller's
tenant and scope are checked independently. Previously issued signed URLs retain
their existing one-hour validity.

Reports reflect source data observed during an attempt. They are not immutable
point-in-time database snapshots: late events or changed review decisions may
alter a retried report. No events or report contents are sent through email or
external notification channels by this flow.

## Capacity and output limits

PDF exports are capped at **5,000 rows**; Excel exports at **50,000 rows**.
Queries fetch one extra row to detect excess and fail explicitly instead of
silently truncating. Excel uses a write-only workbook and stores supplied text
as literal cells, preventing zone names or other labels becoming formulas.
PDF branding text is escaped before layout.

The row ceilings bound work, but do not guarantee completion within two minutes
on every host. Select a shorter period for oversized or slow exports. One child
per API process consumes additional memory, CPU, database connections and
storage bandwidth. Measure this workload alongside detection/control-plane
traffic before increasing API replica counts. A dedicated report deployment can
be considered after measured demand; this change adds no new broker or queue
service.

Successful artifacts are retained using the existing reports bucket. Failed or
superseded uploads are removed when their outcome is known. A hard crash, failed
cleanup or lost database commit response can leave an unreferenced attempt
object; uncertain completion preserves the object to protect any committed
report reference. Configure storage lifecycle/reconciliation for orphaned
objects and incomplete multipart uploads without deleting referenced reports.

## Deployment

1. Back up the database and reports bucket using the established procedure.
2. Run `cd backend && alembic upgrade head`. Migration **0022** adds job fields,
   the due-job index and per-enterprise idempotency constraint.
3. Deploy the backend and frontend. Existing MinIO settings and the existing
   reports bucket are reused; no new secrets or dependencies are required.
4. Verify `/health/ready`: it now also checks that the report dispatcher task
   is running. Startup and readiness both require schema 0022.
5. Request a small PDF and Excel report, observe completion, and download both
   through the site's real HTTPS storage endpoint. Exercise storage outage and
   API restart recovery on an authorized test deployment.

During a coordinated rollback, stop report dispatchers and preserve active jobs
and artifacts first. Downgrading to 0021 removes job/attempt/idempotency fields;
older code cannot resume queued jobs. Prefer a forward fix while work is pending.
No report retention policy or automatic destructive cleanup is introduced.

## Verification boundaries

Regression coverage includes concurrent duplicate admission and queue limits,
date validation, tenant/factory restrictions, restart/expired-lease recovery,
stale progress rejection, retry exhaustion, cancellation, native subprocess
timeout/reaping, actual PDF/Excel rendering, row/date/tenant filtering and caps,
formula-safe exports, requester revocation and ambiguous completion commits.

The subprocess smoke uses real PostgreSQL, the MinIO SDK and a local S3 HTTP
fixture to generate, upload, sign and download a workbook. That fixture does not
validate S3 authentication, TLS or real MinIO behavior. Public MinIO image pulls
from Docker Hub and Quay were denied in this environment; real MinIO/provider
deployment validation remains outstanding. Browser tests use mocked APIs for
queue/progress/retry/download access, history pagination and error recovery.

These checks do not establish factory GPU capacity or change the separate site
acceptance requirements in [FACTORY_PILOT_ACCEPTANCE.md](FACTORY_PILOT_ACCEPTANCE.md).
