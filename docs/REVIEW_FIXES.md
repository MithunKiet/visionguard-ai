# Review remediation — 13 October 2026

This change fixes reproducible security and reliability defects from the [12 October review](reviews/2026-10-12-deep-review.md). It preserves the FastAPI/React/worker architecture. It does **not** certify the system for unattended production use or validate a 200-camera capacity claim.

## Follow-up regression corrections

The follow-up review reproduced two defects in the initial remediation. Manual camera activation now updates an inactive camera, while automatic stream events preserve the inactive state and do not broadcast a discarded status. Logout now revokes the presented refresh credential and clears its cookie even when access has expired or the account is suspended. Only signature-verified access-token IDs can be blacklisted; expiry remains enforced on normal authenticated endpoints. Invalid or absent credentials can complete an idempotent logout without gaining access to any data. Storage/cache failures still fail the logout request rather than reporting unconfirmed revocation as successful.

Regression coverage checks persisted camera state and worker polling after reactivation, ignored transport updates while inactive, logout after expiry/suspension, invalid-signature isolation, refresh-token revocation, cookie deletion, and browser retry after a failed logout. The next operational step is the [2–4 camera pilot plan](PILOT_PLAN.md).

Browser recovery follow-up (18 October 2026): the header/dashboard now share one authenticated WebSocket, reconnect reloads persisted operational views, live-event bursts coalesce HTTP refreshes, and old occupancy expires instead of appearing current after a gap. Session cleanup and a slow-response reconnect race have browser regression coverage. See [LIVE_FEED_RECOVERY.md](LIVE_FEED_RECOVERY.md) for the scope and remaining site tests.

## Deployment and compatibility

- The subsequent [durable alert delivery change](ALERT_DELIVERY.md) requires migration `0018`. It adds transactional delivery jobs, independent retries and administrator status/replay controls. The validation numbers below describe the earlier review remediation; current delivery-specific validation is recorded in that guide.
- Current multi-factory scheduling requires migration `0019` and explicit administrator configuration of each worker's factory and camera budget. Unconfigured workers receive no streams. Follow the coordinated upgrade instructions in [WORKER_SCHEDULING.md](WORKER_SCHEDULING.md).

- Run `alembic upgrade head` before starting the new backend. Migration `0017` adds event receipts, stored review/bounding-box fields, and a PostgreSQL sequence for globally unique alert numbers. Existing data is preserved. Container startup runs migrations under a PostgreSQL advisory lock; readiness rejects an older schema.
- All previously issued access and refresh tokens must be replaced by signing in again. New tokens carry a password-derived, keyed session fingerprint. Password changes invalidate both token types. HTTP authorization reads current roles, scope and account status. WebSocket delivery checks the same policy; idle sockets revalidate every 15 seconds.
- Temporary-password users must change their password before using application endpoints. A password-change screen is included. MFA-enabled accounts fail closed because a complete MFA challenge flow is not implemented. Master-password login is prohibited in production.
- Enterprise-wide report downloads and audit queries are restricted to enterprise/system administrators. Factory managers retain access to their scoped operational data. Durable report/audit scope metadata is needed before granting narrower roles access to those enterprise-wide records.
- Production requires `CAMERA_ALLOWED_HOSTS` as a JSON array of trusted camera hostnames/IP addresses and `WORKER_CREDENTIALS` as a JSON object keyed by worker business ID. Each value contains `enterprise_id` and `key`. Set `WORKER_1_API_KEY` and `WORKER_2_API_KEY` to the corresponding keys. Keep values in the deployment secret store. Shared worker credentials remain a development compatibility option.
- Camera URLs returned to users omit credentials and query parameters. Connection tests for existing cameras use the camera ID; the backend retains the actual URL. Only camera managers may probe a newly submitted RTSP URL. Local file paths and non-RTSP protocols are rejected. Restrict worker/backend network egress to trusted camera networks as well; hostname validation alone cannot prevent DNS rebinding.
- Production Compose requires version 2.24.4 or later for `!reset`/`!override`. It publishes only `127.0.0.1:8080` for the frontend. Put an HTTPS reverse proxy in front of this listener. Configure the public storage endpoint and `MINIO_PUBLIC_SECURE=true`; use `MINIO_SECURE` when the internal S3 endpoint also uses TLS.
- MediaMTX host ports remain private in production. Live Grid now uses a per-asset authenticated HLS gateway with tenant/factory/zone authorization and explicit camera-to-stream mappings. Provision private camera relays, both media secrets and HTTPS before enabling playback; see `docs/SECURE_LIVE_VIDEO.md`. Development listeners bind only to loopback.
- Synthetic PPE detection now requires explicit `DEMO_MODE=true` and is rejected when `ENVIRONMENT=production`. Supply validated PPE weights or a configured remote provider. Remote-provider errors stop inference for that frame instead of becoming false missing-PPE evidence. Local GPU requests fall back to CPU if CUDA is unavailable; performance must still be measured.
- Use Node.js 24 for the frontend toolchain. FastAPI/Starlette and related Python packages have been upgraded; JWT handling now uses PyJWT. Run the complete requirements installation rather than updating individual packages in an existing environment.

## Validation

Executed in the cloud workspace:

- 45 backend tests passed, including 24 PostgreSQL/Redis integration tests. These exercise tenant and factory restrictions, cross-tenant references, live permission changes, logout/suspension/password revocation, concurrent refresh rotation, worker isolation, RTSP restrictions, concurrent replay, transaction rollback, review persistence, config version concurrency, false-positive propagation and Redis fanout across two manager instances. Follow-up cases cover logout with expired/missing/tampered credentials and suspended accounts, plus manual camera reactivation and transport-event handling. Merge regressions also verify all four analytics endpoints for enterprise, factory, zone and empty scopes, and restrict enterprise-wide report access.
- 32 AI tests passed, including clean/uncertain-frame streak resets, duplicate boxes in one frame, empty PPE lists, shoes thresholds, review/mask event mapping, delivery acknowledgement cooldowns and provider-outage handling.
- Four Chromium browser tests passed: mandatory first-password change, server logout with a second tenant login, pagination beyond the first alert page, and retrying logout after a connection failure. Browser API responses are mocked; these do not claim a real-camera or production-domain browser test.
- Backend and configured AI lint checks passed. TypeScript and the Vite production build passed. Vite still reports a large application bundle.
- A fresh disposable PostgreSQL database migrated from empty through `0017`; the existing development database upgraded from `0016` through `0017` without dropping application data.
- Live service smoke passed: dependency readiness, login, RabbitMQ → PostgreSQL → Redis fanout → WebSocket delivery, PDF/XLSX generation with signed downloads, and logout revocation. Temporary smoke data and report objects were removed.
- The production frontend Docker image built successfully and nginx served the SPA and client-side routes. Build dependencies were installed from the lockfile; host `node_modules`, virtual environments and local environment files are excluded from build contexts. The cloud builder required its existing proxy host mapping and trusted CA, with TLS verification preserved.
- The merged production Compose configuration passes `python infra/check_production_config.py`: infrastructure/media ports remain private, development source mounts are removed, and migration startup is selected.
- The installed backend dependency audit and the frontend npm audit report no known vulnerabilities at validation time. This is a point-in-time advisory check, not proof of exploit resistance. The complete GPU inference dependency stack was not installed or audited.

CI now includes the PostgreSQL/Redis integration suite, browser regressions, production Compose validation and a production frontend image build.

## Findings disposition

“Addressed” describes the implemented defect correction, not certification of every deployment scenario. “Partial” identifies a concrete improvement with remaining work. The original dated review remains unchanged as historical evidence.

| Finding | Status | Result and remaining work |
| --- | --- | --- |
| AUTH-01 | Partial | Worker HTTP credentials can be bound to tenant and worker; wrong-tenant lookup/heartbeat denied. Broker credentials/vhosts still need deployment-level producer isolation. |
| AUTH-02 | Addressed | Shared path/body reference policy, scoped collections/analytics, authorized WebSocket delivery; enterprise-wide reports/audit restricted to administrators. Expand the permission matrix as endpoints are added. |
| AUTH-03 | Partial | Request references enforce tenant, soft-deletion and parent hierarchy; current user assignments are checked on updates. Database composite tenant constraints and a complete legacy-data repair remain. |
| AUTH-04 | Addressed | Revoked/inactive/password-changed sessions rejected; roles/scopes refreshed from database; WebSocket revalidation added. |
| AUTH-05 | Addressed | Refresh token consumption and replacement share one locked transaction; concurrent test has exactly one success. |
| AUTH-06 | Addressed | Logout revokes the server session; query caches are cancelled/cleared on session changes; refresh fetches the current profile. |
| AUTH-07 | Partial | Login throttling and mandatory password-change workflow implemented. MFA-enabled accounts are blocked until a real second-factor flow is implemented. |
| AUTH-08 | Addressed | Every HLS asset requires a current authorized session and camera scope; browser media credentials/URLs stay private. Real-camera, TLS and capacity rollout checks remain; see `docs/SECURE_LIVE_VIDEO.md`.
| AUTH-09 | Partial | Camera API/probe responses redact credentials; reader/provider logs omit raw URLs/errors; SQL parameters hidden. Managed camera-secret storage and auditing native library logs remain. |
| AUTH-10 | Partial | RTSP schemes/hosts validated and probing requires a manager role; timeouts added. Deployment egress controls remain necessary. |
| AI-01 | Addressed | Synthetic detections require explicit development opt-in and cannot start in production. |
| AI-02 | Partial | Provider outage/malformed response raises an inference error instead of an empty PPE result. Remote batching, rate limits and calibration still require provider-specific work. |
| AI-03 | Addressed | Clean/uncertain frames break streaks; duplicate boxes do not count as multiple frames. |
| AI-04 | Addressed | Canonical version/PPE fields and camera overrides survive config updates; periodic assignment reconciliation repairs missed pushes. |
| AI-05 | Partial | Empty PPE requirements, shoes threshold and mask event mapping corrected. Catalog entries still cannot create unsupported model capabilities. |
| AI-06 | Addressed | Low-confidence events persist a review flag and do not create automatic alerts. |
| AI-07 | Addressed | Camera assignment/configuration reconciliation runs every 30 seconds; removed/changed assignments stop/restart their tasks. Real RTSP soak testing remains. |
| AI-08 | Partial | Heartbeat freshness filters, stream state events and circuit recovery added. Actual capture latency, cancellation under blocked native IO and long-running recovery need camera testing. |
| AI-09 | Partial | Track IDs/bounding boxes propagate and snapshots use UUID suffixes. Tracking remains camera-local and is not employee identification. |
| AI-10 | Remaining | Define overlapping-camera/ROI ownership before implementing zone-level occupancy aggregation. The dashboard now labels its value as a camera count. |
| AI-11 | Remaining | Supply representative labeled data and establish held-out site/person metrics and model promotion gates. Code changes cannot establish detection accuracy. |
| AI-12 | Partial | CPU fallback added; production documentation uses actual settings. GPU image reproducibility and capacity/freshness benchmarks remain. |
| DATA-01 | Addressed | PostgreSQL allocates alert numbers atomically across tenants; camera-level locks serialize cooldown decisions. |
| DATA-02 | Partial | PPE, overcrowding and camera-quality alert events now commit receipts, alerts and delivery jobs atomically; replay and rollback tested. Non-alert event idempotency and durable config publication remain. |
| DATA-03 | Partial | Config updates lock the row and produce distinct versions; workers reconcile missed pushes. A transactional config outbox remains. |
| DATA-04 | Addressed | Conditional state transitions prevent stale updates; false-positive state propagates to the violation; responses include transition timestamps. |
| DATA-05 | Partial | PPE records and shift lookup use the supplied event timestamp. Factory timezone configuration remains. |
| DATA-06 | Partial | Integer/FK widths and known nullability differences aligned; Alembic includes all schemas. Existing identity/default/index naming differences still make `alembic check` non-clean; do not apply generated changes blindly. |
| DATA-07 | Partial | Deleted/cross-parent references rejected on guarded paths; explicit config capacity clearing supported. Full lifecycle cascade and setup-wizard replay semantics remain. |
| DATA-08 | Addressed | Worker cooldown starts after successful snapshot/event publication. Notifications now use persistent per-channel jobs, bounded retries, status monitoring and administrator replay. Validate the actual providers and burst capacity before production; delivery is at least once. |
| DATA-09 | Partial | Audit failure rolls back its failed transaction; enterprise-wide reads restricted. Durable complete coverage and append-only database permissions remain. |
| SCALE-01 | Partial | Redis distributes live events to every API replica and scope is checked per socket. Browser reconnect now resyncs persisted HTTP views, including a slow-response race. Pub/sub/live-event history remains ephemeral; site ingress/concurrency recovery tests remain. |
| SCALE-02 | Partial | Report generation/upload runs off the event loop; exports exceeding 5000 rows return an explicit error. User-list pagination and batch role loading are implemented; see [USER_DIRECTORY_SCALING.md](USER_DIRECTORY_SCALING.md). Background report jobs and availability-aware scores remain. |
| DEPLOY-01 | Addressed | Compose inheritance uses explicit reset/override and is checked in CI. |
| DEPLOY-02 | Addressed | Frontend Dockerfile uses the correct repository-root paths; production build is included in CI. |
| DEPLOY-03 | Addressed | Container startup runs serialized migrations; schema readiness gates traffic. |
| DEPLOY-04 | Partial | Public storage TLS is configurable and production requires HTTPS; ingress is private by default. Certificates, real public URLs, private camera relays and real-domain playback validation remain deployment work. HLS avoids ICE/TURN. |
| DEPLOY-05 | Remaining | Choose and provision a maintained S3-compatible storage service and verify backup compatibility. The development MinIO source build is not a support policy. |
| DEPLOY-06 | Partial | Readiness checks PostgreSQL/schema, Redis, RabbitMQ and storage and returns HTTP 503 when degraded. Worker freshness alerting/runbooks remain. |
| DEPLOY-07 | Remaining | Define retention/RPO/RTO; implement scheduled offsite backups and run isolated database/object restore drills. |
| SEC-01 | Partial | Current backend/frontend audits clean after controlled upgrades and JWT-library replacement. Audit the full GPU runtime and continue dependency monitoring. |
| UI-01 | Partial | Accurate server alert totals, real alert/violation pagination and activity invalidation fixed. Occupancy aggregation/freshness and aggregate review counts remain. |
| UI-02 | Partial | Shared frontend socket, bounded reconnect/event-refresh timers, session cleanup, immediate HTTP resync and stale-occupancy expiry implemented. Complete role-aware controls/error states remain. |
| PRODUCT-01 | Remaining | Reporting/analytics/settings UI expansion, generic rules, employee identity, recording and model promotion are separate product capabilities. |
| QUALITY-01 | Partial | Added meaningful integration/browser/fault/concurrency coverage and CI gates. Real cameras/GPU, load, TLS, media, restore and long-running fault tests remain. |

## Before a production pilot

Provision maintained object storage and TLS ingress, bind worker credentials to tenants, configure trusted camera networks, supply validated model weights, provision and validate authorized media relays, and validate durable notification delivery with the intended providers and workload. Then test the actual camera placement, lighting, occlusion, PPE types and operating shifts. Measure false-positive/false-negative rates, event latency, missed frames, recovery behavior and GPU memory before choosing a camera-per-worker limit.

Audio recording, continuous video archival, assault detection and identifying a named employee are not implemented by these fixes. Do not infer any of those capabilities from PPE alerts or camera-local track IDs.
