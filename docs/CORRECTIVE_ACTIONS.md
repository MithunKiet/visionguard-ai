# Incident corrective actions

**Alerts → Review** now supports a responsible reviewer, corrective plan, action
due date, photo evidence, completion note and final closure. The Alerts list
shows the corrective due date separately from the severity-based SLA deadline.
**Overdue corrective actions only** filters outstanding plans on the server and
includes open and acknowledged incidents when selected.

## Workflow

1. Select an eligible responsible reviewer, describe the corrective work and
   choose a future due date within 366 days. Dates entered in the browser use
   its timezone and are sent with an explicit UTC offset.
2. Save the plan before attaching photos. Unsaved plan edits must be saved or
   discarded before attaching evidence, completing the action or resolving the
   incident. Server revision checks reject stale edits with 409 and the browser
   retains the draft for review.
3. Attach one or more corrective JPEG/PNG photos to the current plan version.
   A photo from an earlier version remains visible in history but does not
   satisfy the current plan's completion requirement.
4. The responsible person, or a scoped system/enterprise administrator or
   factory manager, enters a nonblank completion note. The action is marked
   complete, while the incident remains open/acknowledged for final review.
5. An authorized incident reviewer checks the outcome and records a closure
   note. A planned action cannot be resolved until completion has been saved.

Editing a saved plan creates another plan version and invalidates previous
completion. Reassigning an incident with an existing plan does the same, so
earlier evidence cannot silently approve changed responsibilities. Repeating
legacy assignment to the same eligible person is a no-op. Closed incidents
cannot be reassigned, replanned or completed through these endpoints.

Marking an incident false positive can close it without completing unnecessary
corrective work; any unfinished plan is shown as cancelled. Already completed
work remains recorded. Incidents without a corrective plan retain their
existing basic-review behavior, including the legacy API's optional resolution
note. The browser still requires a final review note for resolution.

## Permissions and history

System/enterprise administrators, factory managers and safety officers may
create plans and attach photos within their existing incident scope. Eligible
assignees must be active reviewers whose roles and factory permit access to the
incident, and must also be visible within the assigning caller's scope. The
candidate endpoint returns paginated names/public IDs, without directory emails
or other user details. Viewers can inspect permitted plans/photos but cannot
mutate them. A safety officer completes their own assigned action; scoped
administrators/managers can complete it on their behalf, with the actual actor
recorded in history.

Plan changes, assignments, photo attachments and completion notes append typed
events to the existing review history. Those events commit in the same database
transaction as the corresponding mutation. Status transitions lock the same
incident row, preventing a concurrent plan save and resolution from both
bypassing the completion requirement. Revision comparison protects plan,
attachment and completion requests. General audit records retain their existing
best-effort behavior; the incident's transactional history is the authoritative
workflow record for these changes.

Evidence records are immutable through the API. Plan version, actor, original
filename, byte count and SHA-256 are retained. Hash verification checks stored
byte consistency; a reviewer remains responsible for confirming the work shown
by the photo. Original bytes and metadata are preserved. Uploading an image
does not establish that it was captured at this factory or at a particular time.

## API

All paths below are relative to `/api/v1/alerts/{alert_id}` and enforce current
tenant/factory/zone access.

| Path | Contract |
| --- | --- |
| `GET /corrective-action` | Current plan, revision, overdue/completion status and evidence metadata. |
| `GET /assignees` | Eligible reviewers, with `search`, `page` and `page_size` (20 default, 100 maximum). |
| `PUT /corrective-action` | `assigned_to`, `description`, timezone-aware `due_at`, `expected_revision`. |
| `POST /corrective-action/evidence` | Multipart `file`, UUID `upload_id`, and `expected_revision`. |
| `POST /corrective-action/complete` | Nonblank `note` and `expected_revision`. |
| `GET /corrective-action/evidence/{evidence_id}` | Authenticated image download; rechecks access on each request. |

The legacy `/assign` endpoint remains available, now validates recipient access,
records assignment history and invalidates an existing plan's completion when
the assignee changes. It returns the refreshed assignment/action state. New
plans and attachments should use the versioned corrective endpoints.

`GET /api/v1/alerts?corrective_overdue=true` returns only open/acknowledged
incidents whose corrective due date has passed and whose action is incomplete.
Existing status, severity, tenant and location filters still apply. Responses
add `action_planned`, `action_due_at` and `action_completed_at`.

## Photo handling and storage

Each photo is limited to **5 MiB**, **20 megapixels**, and a single JPEG/PNG
frame. File type is checked by decoding the image rather than trusting its name
or declared MIME type. The multipart request is capped at **6 MiB** including
form fields, even when its total length is not supplied up front. Multipart
scope checks do not buffer the request as JSON.

At most **50 photos per incident** are retained across all plan versions. At
that limit, additional uploads and plan/reassignment changes requiring another
photo are rejected, preserving a completable existing plan. The cap does not
delete earlier evidence. Plan records and the existing photos can still be
reviewed and the current action completed.

Files use the existing private snapshots bucket under a separate corrective
prefix. Upload/read operations have finite storage timeouts and do not retain
a database connection during network I/O. A UUID upload reference makes retries
of the same file idempotent after a lost HTTP response. Each storage attempt
also has a unique object key, preventing a concurrent retry from overwriting
bytes already referenced by committed evidence.

The image endpoint returns original bytes only after current access and stored
size/hash checks. Responses use `Cache-Control: no-store`, a fixed image content
type, `nosniff` and a generated attachment filename. The frontend fetches images
with authenticated requests, clears denied previews and releases object URLs.
It does not publish permanent or presigned corrective-photo links. Bytes that
a person already downloaded cannot be revoked from their device.

A storage timeout, conflicting edit or uncertain database commit may leave an
unreferenced object. These objects are deliberately retained rather than risking
deleting evidence whose commit succeeded but whose response was lost. Reconcile
orphaned objects against database references before deletion. Do not apply a
blanket expiration rule that would remove referenced corrective evidence.
Include the evidence table and corrective snapshot prefix in backups and
storage-capacity planning; 50 maximum-size photos can consume 250 MiB per
incident. No automatic destructive retention cleanup is introduced.

## Deployment and verification

Back up the database/snapshots bucket, install the pinned backend requirements,
run `cd backend && alembic upgrade head`, then deploy backend and frontend.
Migration **0024** adds corrective fields, typed history metadata and the
evidence table. Pillow is now explicitly pinned at 12.3.0, matching the tested
environment. No new bucket or secrets are required. Startup/readiness use 0024.

Use an authorized pilot incident to verify assignment, due-date display,
upload/download, completion and closure. Check an overdue action, a failed
storage operation, competing edits and an account whose access was revoked.
No new assignment email, external notification, automated escalation or physical
corrective verification is sent/performed by this workflow.

Tests exercise real PostgreSQL persistence/rollback, role/location isolation,
revision races, photo validation/body limits, retry identity, quota behavior,
authenticated hash-checked reads and closure gates. A local S3 HTTP fixture
exercises the real MinIO SDK upload/download transport; it does not validate
production MinIO authentication or TLS. Real provider/site acceptance remains
separate. Browser tests cover the complete review workflow, retained drafts,
lost upload responses, denied previews, viewer access and the overdue filter.

Prefer forward fixes. Downgrading to 0023 drops corrective plans, typed history
details and evidence references. Stop upgraded writers and preserve these
records and their object mapping before any coordinated rollback; do not remove
metadata while evidence is still required.
