# VisionGuard AI — Deep technical review

Review date: 12 October 2026. Reviewed repository: MithunKiet/visionguard-ai. Reviewed commit: aa7868ccb277c9ded8712d285b3f31e776c0e0ce.

**निर्णय: Development environment कार्यरत है। Application को अभी production-ready नहीं माना जा सकता।** अच्छे module boundaries, typed APIs, migrations, durable messaging, authentication primitives और working dashboard/report flow के बावजूद authorization, event integrity और actual PPE behavior में release-blocking defects हैं।

इस report में **45 grouped findings** हैं: 28 P1 और 17 P2। एक finding में निकट-संबंधित कई defects हो सकते हैं। **25 targeted reproduction checks** में undesired behavior reproduce हुआ; इन्हें readiness के passing tests न समझें।

P1 = production/customer exposure से पहले address करें। P2 = operational reliability, accurate workflows और maintainability के लिए आवश्यक काम; relevant acceptance gate पर block करें। Severity deployment context पर निर्भर है—current cloud services loopback development setup हैं।

## Review scope and evidence

Backend auth/RBAC/tenant checks, CRUD/services/repositories, database models and migrations, alert/PPE/occupancy flows, worker detection/config/health, model-training scripts, frontend auth/cache/pages/live feed, Compose/Docker/nginx/media/storage, notifications, backup/monitoring and dependency/CI configuration inspect की गई। Inventory में 195 nonempty source/config files हैं; critical execution paths की manual review और structural searches किए गए।

Reproductions के लिए अलग temporary PostgreSQL database बनाया गया; original development data नहीं बदला। Backend probes ने actual repository functions और ASGI routes use किए। External notification delivery stubbed थी; कोई email/Slack message नहीं भेजा गया। AI checks ने actual validator/config-sync functions exercise किए; real GPU/model inference नहीं चलाया।

Code analysis से हर संभावित defect के न मिलने की guarantee नहीं बनती। वास्तविक camera footage, GPU load, browser E2E, production-domain TLS/ICE, populated-data upgrades और disaster-recovery drills अभी acceptance work हैं। Report में reproduced, source-confirmed और unrun validation स्पष्ट अलग हैं।

## Existing capability baseline

| Workflow/check | Evidence/outcome |
|---|---|
| Backend tests | Earlier onboarding: 21 passed; 16% overall coverage |
| AI unit tests | Earlier onboarding: 25 passed; configured AI lint passed |
| Frontend | TypeScript/Vite build passed; development HTML/module served; bundle warning |
| Infrastructure | PostgreSQL migration 0016, Redis operations, RabbitMQ roundtrip and source-built MinIO worked |
| Live backend | Full startup, health/OpenAPI, auth and representative database APIs passed |
| Reports/storage | Actual PDF/Excel generated, stored and signed downloads passed |
| Synthetic event flow | RabbitMQ → violation → Critical alert → WebSocket → API passed |
| Startup repeatability | Saved startup script restarted native services and repeat API/storage checks passed |
| Backend CI lint | Two pre-existing F401 errors; CI not fully green |
| New reproduction checks | 15 backend + 7 AI + 3 concurrency/protocol checks reproduced defects |
| Database check | Fresh head migrated successfully; Alembic check failed; schema-aware reflection found width/nullability drift |
| Package audits | npm: 10 affected package entries; resolved backend: 8 affected packages |

Source, manifests, lockfiles and repository tests were left unchanged. Review evidence is retained beside this document; reproduction helpers ran outside the checkout. Existing suites passing does not establish authorization correctness, true PPE accuracy or 200-camera capacity.

## Prioritized inventory

| ID | Priority | Finding | Evidence |
|---|---|---|---|
| AUTH-01 | P1 | Worker tenant isolation टूटती है | Reproduced earlier; source confirmed |
| AUTH-02 | P1 | Factory/zone permissions सभी endpoints पर लागू नहीं हैं | Reproduced |
| AUTH-03 | P1 | Cross-tenant foreign keys स्वीकार होते हैं | Reproduced |
| AUTH-04 | P1 | Logout और suspension पुराने access tokens नहीं रोकते | Reproduced |
| AUTH-05 | P1 | Refresh token rotation concurrent requests में single-use नहीं है | Reproduced |
| AUTH-06 | P1 | Frontend logout server को logout नहीं करता; query cache tenant-aware नहीं है | Source confirmed; browser behavior not exercised |
| AUTH-07 | P1 | Login abuse और mandatory password-change controls अधूरे हैं | Source confirmed |
| AUTH-08 | P1 | Live video app permissions को bypass कर सकता है | Source confirmed; media server not started for this review |
| AUTH-09 | P1 | Camera/provider credentials responses और logs में leak हो सकते हैं | Source confirmed |
| AUTH-10 | P1 | RTSP test endpoint arbitrary file/protocol input स्वीकार करता है | Reproduced protocol-validation failure; no external exploit attempted |
| AI-01 | P1 | Trained model के बिना synthetic violations बनते हैं | Source confirmed |
| AI-02 | P1 | Remote inference failure false PPE violations में बदल सकती है | Source confirmed; remote outage not tested on a real provider |
| AI-03 | P1 | Consecutive-frame voting वास्तव में consecutive नहीं है | Reproduced |
| AI-04 | P1 | Initial और hot-reload config contracts mismatch हैं | Reproduced with real config-sync/validator functions |
| AI-05 | P1 | PPE selection/threshold handling में तीन अलग bugs हैं | Reproduced |
| AI-06 | P1 | Low-confidence review events silently drop होते हैं | Reproduced |
| AI-07 | P1 | Camera assignment/update/delete running worker में reconcile नहीं होते | Source confirmed |
| AI-08 | P2 | Camera/worker failure status और recovery अधूरे हैं | Source confirmed |
| AI-09 | P2 | Person evidence में track/bbox/model identity सुरक्षित नहीं रहती | Track-id omission reproduced; other details source confirmed |
| AI-10 | P2 | Zone occupancy में multi-camera/ROI semantics नहीं हैं | Source confirmed |
| AI-11 | P1 | Model quality gate deployment को रोकती नहीं है | Source confirmed; model training not run |
| AI-12 | P2 | CPU/GPU/runtime sizing का reproducible contract नहीं है | Source confirmed; hardware benchmarks unrun |
| DATA-01 | P1 | Alert numbers tenants के बीच collide करते हैं | Reproduced |
| DATA-02 | P1 | Events idempotent/transactional नहीं हैं | Duplicate replay reproduced; partial-commit behavior source confirmed |
| DATA-03 | P1 | Config version increment और publication atomic नहीं हैं | Reproduced concurrency; delivery failure risk source confirmed |
| DATA-04 | P2 | False-positive data और transition responses inconsistent हैं | Reproduced; transition race source confirmed |
| DATA-05 | P2 | Capture/event time और factory-local shift time गलत interpret हो सकते हैं | Event-time loss reproduced; timezone gap source confirmed |
| DATA-06 | P2 | ORM और migrated schema drift; Alembic autogeneration unsafe है | Schema-aware reflection confirmed |
| DATA-07 | P2 | Hierarchy lifecycle और input validation अधूरे हैं | Source confirmed |
| DATA-08 | P2 | Queue delivery और notifications की recovery अधूरी है | Source confirmed |
| DATA-09 | P2 | Audit append-only guarantee और coverage अधूरी है | Source confirmed |
| SCALE-01 | P1 | Multiple backend instances में live event delivery सही नहीं होगी | Source topology confirmed |
| SCALE-02 | P2 | Blocking report/storage operations और unbounded list/export semantics | Source confirmed; load tests unrun |
| DEPLOY-01 | P1 | Production overlay public ports और dev mounts retain करती है | Rendered Compose configuration confirmed |
| DEPLOY-02 | P1 | Production frontend Dockerfile wrong build context paths use करती है | Source paths confirmed; image build unrun |
| DEPLOY-03 | P1 | Repository Docker startup migrations नहीं चलाता | Source confirmed; fresh Docker boot unrun |
| DEPLOY-04 | P1 | TLS/public URLs और remote WebRTC configuration अधूरी है | Source confirmed; real-domain/ICE deployment unrun |
| DEPLOY-05 | P1 | MinIO distribution/maintenance dependency अब unreliable है | Download/pull failure observed earlier; source build validated |
| DEPLOY-06 | P2 | Readiness केवल Redis जाँचती है; incident alerts configured नहीं हैं | Source confirmed; production health-failure injection unrun |
| DEPLOY-07 | P2 | Retention, backup verification और recovery guarantees absent हैं | Source confirmed; backup/restore drills unrun |
| SEC-01 | P1 | Known dependency advisories को address करना जरूरी है | Package audits executed; exploitability not proven |
| UI-01 | P2 | Alerts/violations pagination और dashboard counts गलत scale होते हैं | Source confirmed; browser E2E unrun |
| UI-02 | P2 | WebSocket cleanup और session UI state असंगत है | Source confirmed; browser behavior unrun |
| PRODUCT-01 | P2 | Advertised capability और delivered UI/logic में gaps हैं | API/router/code inventory confirmed |
| QUALITY-01 | P2 | Passing unit tests production behavior cover नहीं करतीं | Existing suites/build/lint executed earlier; targeted checks this review |

## Findings, fixes and acceptance checks

### AUTH-01 — Worker tenant isolation टूटती है

**Priority:** P1. **Evidence:** Reproduced earlier; source confirmed.

Worker-camera lookup tenant context को ignore करता है। Heartbeat भी worker_id alone से existing worker update करता है और caller enterprise को response में दर्शाता है; shared key के साथ दूसरे tenant की identity/data प्रभावित हो सकती है।

**काम:** Worker identity को enterprise के साथ resolve करें; per-worker scoped credentials और event authorization लागू करें।

**Fix verify कैसे करें:** Wrong enterprise/worker combination पर 403/404, camera URLs न लौटें और दूसरे tenant की heartbeat row न बदले।

**Source:** [backend/src/modules/worker/api/routes.py:58](../../backend/src/modules/worker/api/routes.py#L58); [backend/src/modules/worker/infrastructure/repositories.py:55](../../backend/src/modules/worker/infrastructure/repositories.py#L55)

### AUTH-02 — Factory/zone permissions सभी endpoints पर लागू नहीं हैं

**Priority:** P1. **Evidence:** Reproduced.

Factory manager ने दूसरी factory पढ़ी/बदली, उसके zone config पढ़े, maintenance mode से alerts suppress किए और camera create किया। Factory/department detail/mutation, config, maintenance, shifts, notifications, analytics, reports और WebSocket में narrower scope लगातार लागू नहीं होता।

**काम:** एक साझा authorization policy से read, create, update और service-to-service paths में tenant + factory + zone scope enforce करें।

**Fix verify कैसे करें:** दो factories और zone-scoped viewer वाली permission matrix में हर operation के allow/deny checks हों; maintenance suppression भी scope-protected हो।

**Source:** [backend/src/modules/factory/api/routes.py:53](../../backend/src/modules/factory/api/routes.py#L53); [backend/src/modules/maintenance/api/routes.py:60](../../backend/src/modules/maintenance/api/routes.py#L60); [backend/src/modules/config/api/routes.py:29](../../backend/src/modules/config/api/routes.py#L29)

### AUTH-03 — Cross-tenant foreign keys स्वीकार होते हैं

**Priority:** P1. **Evidence:** Reproduced.

Tenant A department और shift में tenant B factory स्वीकार हुई; tenant A notification recipient में tenant B user स्वीकार हुआ। Generic to_pk केवल ID resolve करता है, ownership नहीं। User factory/department/assigned zones, plant heads, supervisors और alert assignees पर भी यही validation चाहिए।

**काम:** हर referenced entity की tenant और parent hierarchy validate करें; जहाँ संभव हो composite tenant-aware constraints जोड़ें।

**Fix verify कैसे करें:** Cross-tenant references 4xx से reject हों; notification किसी दूसरे tenant के user तक न जाए; foreign factory/department/zone combinations भी reject हों।

**Source:** [backend/src/shared/database/pid.py:15](../../backend/src/shared/database/pid.py#L15); [backend/src/modules/department/infrastructure/repositories.py:46](../../backend/src/modules/department/infrastructure/repositories.py#L46); [backend/src/modules/users/infrastructure/repositories.py:61](../../backend/src/modules/users/infrastructure/repositories.py#L61); [backend/src/modules/notifications/infrastructure/repositories.py:41](../../backend/src/modules/notifications/infrastructure/repositories.py#L41)

### AUTH-04 — Logout और suspension पुराने access tokens नहीं रोकते

**Priority:** P1. **Evidence:** Reproduced.

Logout 200 के बाद token /auth/me पर चला। Account Inactive करने के बाद भी पुराना token चला। Authorization JWT signature/type पढ़ती है; Redis blacklist, current account status और changed roles/scope नहीं जाँचती। WebSocket authentication केवल handshake पर होती है।

**काम:** Revocation/session version और account/role changes enforce करें; active WebSocket sessions को expire/revoke करें।

**Fix verify कैसे करें:** Logout, deactivate, password/security reset और permission removal के बाद पुराने HTTP/WS access reject हों।

**Source:** [backend/src/shared/security/dependencies.py:39](../../backend/src/shared/security/dependencies.py#L39); [backend/src/modules/identity/application/services.py:126](../../backend/src/modules/identity/application/services.py#L126); [backend/src/modules/realtime/routes.py:14](../../backend/src/modules/realtime/routes.py#L14)

### AUTH-05 — Refresh token rotation concurrent requests में single-use नहीं है

**Priority:** P1. **Evidence:** Reproduced.

एक refresh token की चार concurrent requests में दो HTTP 200 responses मिले। Validation और revocation अलग commits हैं; SELECT में lock/atomic consume नहीं है।

**काम:** Atomic conditional update/row lock से token consume करें; rotation परिवार और reuse handling तय करें।

**Fix verify कैसे करें:** Concurrent renewal में exactly one success; old token replay denied; transaction failure orphaned/extra valid tokens न बनाए।

**Source:** [backend/src/modules/identity/application/services.py:88](../../backend/src/modules/identity/application/services.py#L88)

### AUTH-06 — Frontend logout server को logout नहीं करता; query cache tenant-aware नहीं है

**Priority:** P1. **Evidence:** Source confirmed; browser behavior not exercised.

AppShell logout केवल local session clear और navigate करता है; refresh cookie/server session untouched रहते हैं। Shared QueryClient clear नहीं होता और keys में user/tenant नहीं है; cached branding दस मिनट तक previous tenant की दिख सकती है और other cached lists briefly दिख सकती हैं।

**काम:** Server logout await करें, cookie revoke करें, auth transitions पर cancel/clear queries करें और user/tenant-qualified keys रखें।

**Fix verify कैसे करें:** Same tab में A logout → B login पर A का cached data न दिखे; logout के बाद silent refresh denied हो।

**Source:** [frontend/src/components/AppShell.tsx:111](../../frontend/src/components/AppShell.tsx#L111); [frontend/src/main.tsx:15](../../frontend/src/main.tsx#L15); [frontend/src/api/client.ts:27](../../frontend/src/api/client.ts#L27)

### AUTH-07 — Login abuse और mandatory password-change controls अधूरे हैं

**Priority:** P1. **Evidence:** Source confirmed.

Application-level login throttling/lockout नहीं मिला। is_first_login flag लौटता है लेकिन frontend सीधे dashboard खोलता है; backend temporary-password sessions को password-change तक सीमित नहीं करता। totp_enabled/pyotp मौजूद हैं, लेकिन MFA verification flow नहीं मिला।

**काम:** Login abuse controls और forced first-password-change flow लागू करें। MFA को वास्तव में implement करें या unsupported capability स्पष्ट करें।

**Fix verify कैसे करें:** Repeated failed login bounded हो; first-login user privileged operations न करे जब तक password बदले; MFA-enabled login second factor मांगे।

**Source:** [backend/src/modules/identity/application/services.py:39](../../backend/src/modules/identity/application/services.py#L39); [frontend/src/pages/Login.tsx:33](../../frontend/src/pages/Login.tsx#L33); [backend/src/core/app.py:10](../../backend/src/core/app.py#L10)

### AUTH-08 — Live video app permissions को bypass कर सकता है

**Priority:** P1. **Evidence:** Source confirmed; media server not started for this review.

MediaMTX reads intentionally unauthenticated हैं और WebRTC ports published हैं। App में login से camera visibility control करने पर भी direct video path की authorization नहीं बनती।

**काम:** Streaming layer में scoped short-lived access/session authorization रखें; publish/read accounts अलग करें और direct unauthenticated access रोकें।

**Fix verify कैसे करें:** Logged-out client तथा wrong tenant direct viewer/WebRTC requests से video न पढ़ें; authorized assigned users stream पढ़ सकें।

**Source:** [infra/mediamtx/mediamtx.yml:27](../../infra/mediamtx/mediamtx.yml#L27); [docker-compose.yml:91](../../docker-compose.yml#L91); [frontend/src/pages/LiveGrid.tsx:159](../../frontend/src/pages/LiveGrid.tsx#L159)

### AUTH-09 — Camera/provider credentials responses और logs में leak हो सकते हैं

**Priority:** P1. **Evidence:** Source confirmed.

API raw rtsp_url लौटाती है, जिसमें username/password हो सकते हैं। FrameReader connection log वही URL लिखता है। Roboflow HTTP exception str में api_key query URL शामिल हो सकती है और उसे log किया जाता है।

**काम:** Credentials URLs से अलग सुरक्षित bindings में रखें; display/response/logs redact करें; HTTP error logging से sensitive parameters हटाएँ।

**Fix verify कैसे करें:** Credential-bearing test URL/key sentinel responses और logs में न मिले; camera access का secret केवल आवश्यक service को मिले।

**Source:** [backend/src/modules/camera/api/routes.py:168](../../backend/src/modules/camera/api/routes.py#L168); [ai-worker/src/pipeline/frame_reader.py:76](../../ai-worker/src/pipeline/frame_reader.py#L76); [ai-worker/src/pipeline/remote_ppe_client.py:52](../../ai-worker/src/pipeline/remote_ppe_client.py#L52)

### AUTH-10 — RTSP test endpoint arbitrary file/protocol input स्वीकार करता है

**Priority:** P1. **Evidence:** Reproduced protocol-validation failure; no external exploit attempted.

Viewer ने rtsp_url में स्थानीय JPEG path दिया और endpoint ने reachable=true लौटाया। Schema plain str है और OpenCV arbitrary input खोलता है; protocol/network restriction तथा endpoint-specific probe timeout/rate control नहीं है।

**काम:** Only supported streaming protocols और approved camera hosts/subnets allow करें; local file paths तथा unrelated internal destinations reject करें। Factory camera private subnets को blanket-block न करें।

**Fix verify कैसे करें:** Local paths/file/http metadata destinations reject हों; allowed real RTSP cameras काम करें; slow probe bounded समय में समाप्त हो।

**Source:** [backend/src/modules/camera/api/schemas.py:34](../../backend/src/modules/camera/api/schemas.py#L34); [backend/src/modules/camera/application/services.py:229](../../backend/src/modules/camera/application/services.py#L229)

### AI-01 — Trained model के बिना synthetic violations बनते हैं

**Priority:** P1. **Evidence:** Source confirmed.

Default fallback generic COCO person detection के ऊपर rotating fake helmet/vest/gloves/shoes violations बनाता है। Demo wiring का pass होना real PPE accuracy साबित नहीं करता। Production-mode model capability guard नहीं मिला।

**काम:** Explicit demo mode रखें; production में validated PPE artifact और class-map manifest आवश्यक करें; synthetic records unmistakably label करें।

**Fix verify कैसे करें:** Missing/incorrect production model पर inference fail closed या unavailable state दिखाए; synthetic evidence real compliance reports में न मिले।

**Source:** [ai-worker/src/pipeline/detector.py:133](../../ai-worker/src/pipeline/detector.py#L133)

### AI-02 — Remote inference failure false PPE violations में बदल सकती है

**Priority:** P1. **Evidence:** Source confirmed; remote outage not tested on a real provider.

Roboflow failure [] returns करती है। Detector no item detected को item missing समझता है; इसलिए quota/timeout/network failure helmet/vest false positives बना सकती है। Batch में remote requests serial हैं, जिससे latency भी बढ़ती है।

**काम:** Inference error और valid empty prediction अलग करें; degraded state/metrics दें; bounded concurrency और latency budget रखें।

**Fix verify कैसे करें:** Provider 429/503/timeout पर synthetic missing-PPE alert न बने; failure visible हो और recovery पर normal detection लौटे।

**Source:** [ai-worker/src/pipeline/remote_ppe_client.py:51](../../ai-worker/src/pipeline/remote_ppe_client.py#L51); [ai-worker/src/pipeline/detector.py:203](../../ai-worker/src/pipeline/detector.py#L203)

### AI-03 — Consecutive-frame voting वास्तव में consecutive नहीं है

**Priority:** P1. **Evidence:** Reproduced.

Positive → clean → positive → clean → positive sequence से required_frames=3 violation निकला। Missing detection के frame में previous per-track counter reset नहीं होता; medium-confidence path भी high-confidence streak नहीं तोड़ता।

**काम:** हर frame में सभी active track/item streaks update/reset करें और confidence-state transition स्पष्ट करें।

**Fix verify कैसे करें:** तीन uninterrupted positive frames पर ही confirmation; clean/absent/insufficient-confidence frames streak reset करें।

**Source:** [ai-worker/src/pipeline/ppe_validator.py:108](../../ai-worker/src/pipeline/ppe_validator.py#L108)

### AI-04 — Initial और hot-reload config contracts mismatch हैं

**Priority:** P1. **Evidence:** Reproduced with real config-sync/validator functions.

Initial worker config में ppe_required/config_version हैं; hot config में required_ppe_types/version। Initial version=5 ने stale hot version=2 स्वीकार किया। Hot replacement effective per-camera overrides खो देता है और validator default helmet/vest पर लौट सकता है।

**काम:** एक versioned validated config DTO use करें; effective camera PPE compute करें; सभी producer/consumer keys और event version semantics समान करें।

**Fix verify कैसे करें:** Initial and hot config equivalent behavior दें; stale updates reject हों; camera overrides तथा changed PPE list reload के बाद सुरक्षित रहें।

**Source:** [backend/src/modules/worker/application/services.py:63](../../backend/src/modules/worker/application/services.py#L63); [backend/src/modules/config/application/services.py:150](../../backend/src/modules/config/application/services.py#L150); [ai-worker/src/config/zone_sync.py:67](../../ai-worker/src/config/zone_sync.py#L67)

### AI-05 — PPE selection/threshold handling में तीन अलग bugs हैं

**Priority:** P1. **Evidence:** Reproduced.

ppe_required=[] को defaults बना दिया जाता है। shoes_threshold=.99 के बावजूद .80 no_safety_shoes detection accepted हुई क्योंकि lookup safety_shoes_threshold मांगता है। no_mask event mapping नहीं है; custom catalog entries से model support स्वतः नहीं आता।

**काम:** Empty और omitted config अलग रखें; canonical item/class/threshold mapping तथा model capability validation जोड़ें।

**Fix verify कैसे करें:** No PPE selected → no PPE violations; shoes threshold सही लागू हो; mask/custom unsupported classes UI/API में स्पष्ट रहें।

**Source:** [ai-worker/src/pipeline/ppe_validator.py:117](../../ai-worker/src/pipeline/ppe_validator.py#L117); [ai-worker/src/pipeline/ppe_validator.py:138](../../ai-worker/src/pipeline/ppe_validator.py#L138); [backend/src/modules/ppe_types/application/services.py:28](../../backend/src/modules/ppe_types/application/services.py#L28)

### AI-06 — Low-confidence review events silently drop होते हैं

**Priority:** P1. **Evidence:** Reproduced.

Worker events.low_confidence_violation publish करता है; backend dispatch इसे handle नहीं करता। Event unhandled warning के बाद process context normally exits, इसलिए message acknowledged हो सकती है और review record नहीं बनता।

**काम:** Review event schema/handler और persistent review lifecycle implement करें; unsupported events की explicit failure/DLQ policy रखें।

**Fix verify कैसे करें:** Low-confidence event durable review record बनाए और operator approve/reject कर सके; replay idempotent हो।

**Source:** [ai-worker/src/pipeline/camera_worker.py:145](../../ai-worker/src/pipeline/camera_worker.py#L145); [backend/src/shared/messaging/consumer.py:63](../../backend/src/shared/messaging/consumer.py#L63)

### AI-07 — Camera assignment/update/delete running worker में reconcile नहीं होते

**Priority:** P1. **Evidence:** Source confirmed.

Worker cameras केवल startup पर fetch करता है। Config sync सिर्फ zone config और camera status संभालता है। New camera assignments, RTSP edits, deletion और model_updated events running task/model lifecycle को update नहीं करते।

**काम:** Periodic reconciliation plus assignment/model events से camera tasks create/update/stop करें; validated atomic model swap implement करें।

**Fix verify कैसे करें:** Running worker में camera add/delete/URL-change बिना restart लागू हों; failed swap old model सुरक्षित रखे।

**Source:** [ai-worker/src/main.py:83](../../ai-worker/src/main.py#L83); [ai-worker/src/config/zone_sync.py:52](../../ai-worker/src/config/zone_sync.py#L52); [backend/src/modules/camera/application/services.py:109](../../backend/src/modules/camera/application/services.py#L109)

### AI-08 — Camera/worker failure status और recovery अधूरे हैं

**Priority:** P2. **Evidence:** Source confirmed.

Normal RTSP disconnect FrameReader में retry होता है लेकिन corresponding offline/reconnected event publish नहीं मिला। mark_offline caller नहीं मिला; list_active केवल status Online देखता है, heartbeat age नहीं। Circuit-open camera का automatic rearm नहीं है। Spec checks cached initial stream properties पढ़ते हैं।

**काम:** Heartbeat expiry supervision, stream state events, recovery/reassignment और live feed quality measurements implement करें।

**Fix verify कैसे करें:** RTSP/worker disconnect पर bounded time में dashboard offline हो; stale worker को new cameras न मिलें; recovered stream/task स्वतः वापिस आए।

**Source:** [ai-worker/src/pipeline/frame_reader.py:108](../../ai-worker/src/pipeline/frame_reader.py#L108); [backend/src/modules/worker/infrastructure/repositories.py:37](../../backend/src/modules/worker/infrastructure/repositories.py#L37); [ai-worker/src/pipeline/camera_worker.py:18](../../ai-worker/src/pipeline/camera_worker.py#L18)

### AI-09 — Person evidence में track/bbox/model identity सुरक्षित नहीं रहती

**Priority:** P2. **Evidence:** Track-id omission reproduced; other details source confirmed.

Validator internally per-person tracking करता है लेकिन confirmed output track_id नहीं देता। CameraWorker published event में bbox भी omit करता है। Snapshot key second-resolution timestamp पर आधारित है, जिससे same camera/type writes collide हो सकते हैं। Current tracker IOU based है; employee identity recognition नहीं है।

**काम:** Track ID, bbox, capture time, model/config version और unique event-based snapshot key persist करें; employee identification को अलग capability मानें।

**Fix verify कैसे करें:** Two simultaneous people के violations uniquely attributable हों; same-second evidence overwrite न हो; API relevant person annotation लौटाए।

**Source:** [ai-worker/src/pipeline/ppe_validator.py:151](../../ai-worker/src/pipeline/ppe_validator.py#L151); [ai-worker/src/pipeline/camera_worker.py:156](../../ai-worker/src/pipeline/camera_worker.py#L156); [ai-worker/src/pipeline/camera_worker.py:257](../../ai-worker/src/pipeline/camera_worker.py#L257)

### AI-10 — Zone occupancy में multi-camera/ROI semantics नहीं हैं

**Priority:** P2. **Evidence:** Source confirmed.

Current occupancy latest reading per zone चुनती है; camera counts aggregate/deduplicate नहीं करती। Worker पूरे frame के persons गिनता है, zone polygon/ROI नहीं मिला। Zone.max_occupancy और ZoneConfig.max_occupancy अलग-अलग update हो सकते हैं।

**काम:** Zone geometry और camera overlap policy तय करें; canonical capacity field, aggregation and freshness state लागू करें।

**Fix verify कैसे करें:** दो non-overlapping cameras का correct zone total मिले; overlapping views double count न करें; capacity update worker और UI में एक साथ लागू हो।

**Source:** [backend/src/modules/occupancy/infrastructure/repositories.py:34](../../backend/src/modules/occupancy/infrastructure/repositories.py#L34); [ai-worker/src/pipeline/camera_worker.py:167](../../ai-worker/src/pipeline/camera_worker.py#L167); [backend/src/modules/zone/application/services.py:129](../../backend/src/modules/zone/application/services.py#L129)

### AI-11 — Model quality gate deployment को रोकती नहीं है

**Priority:** P1. **Evidence:** Source confirmed; model training not run.

Training script metrics print करके best.pt copy कर देता है; documented helmet mAP threshold और held-out factory footage gate enforce नहीं होता। Dataset preparation random image split करता है, जिससे neighboring video frames train/val में leak हो सकते हैं। Model class-ID compatibility validation नहीं मिली।

**काम:** Grouped camera/video/site splits, held-out tests और enforced per-class deployment gate रखें; artifact checksum, class map और rollback manifest रखें।

**Fix verify कैसे करें:** Below-target/unsupported model deploy न हो; target factory की unseen footage पर precision/recall, false-alert rate और per-class performance report हो।

**Source:** [ai-worker/training/train.py:55](../../ai-worker/training/train.py#L55); [ai-worker/training/train.py:60](../../ai-worker/training/train.py#L60); [ai-worker/training/prepare_dataset.py:46](../../ai-worker/training/prepare_dataset.py#L46); [ai-worker/src/pipeline/detector.py:71](../../ai-worker/src/pipeline/detector.py#L71)

### AI-12 — CPU/GPU/runtime sizing का reproducible contract नहीं है

**Priority:** P2. **Evidence:** Source confirmed; hardware benchmarks unrun.

README DEVICE=cpu बताता है, लेकिन actual setting USE_GPU है। Detector requested cuda पर .to(device) करता है; automatic GPU availability fallback नहीं दिखा। Compose GPU reservation mandatory है और torch/model/runtime compatibility fully pinned नहीं है। Frame freshness/backpressure और target capacity benchmark नहीं हुआ।

**काम:** CPU/GPU profiles, compatible pinned inference stack और explicit capability checks दें; oldest-frame age, throughput, memory and dropped-frame metrics benchmark करें।

**Fix verify कैसे करें:** CPU-only documented command काम करे; absent GPU पर clear startup behavior हो; target camera load पर agreed p95 latency/freshness और resource limits meet हों।

**Source:** [README.md:278](../../README.md#L278); [ai-worker/src/config/settings.py:17](../../ai-worker/src/config/settings.py#L17); [ai-worker/src/pipeline/detector.py:150](../../ai-worker/src/pipeline/detector.py#L150); [ai-worker/requirements.txt:2](../../ai-worker/requirements.txt#L2)

### DATA-01 — Alert numbers tenants के बीच collide करते हैं

**Priority:** P1. **Evidence:** Reproduced.

next_sequence tenant-wise COUNT+1 है, लेकिन ALT-year-sequence globally unique है। Tenant A और B का पहला alert same number बनता है; B की creation IntegrityError से fail हुई। Concurrent same-tenant creation में भी race है।

**काम:** Atomic sequence plus tenant/year namespace या globally unique identifier अपनाएँ; dedup race भी atomic करें।

**Fix verify कैसे करें:** दो tenants के first alerts और parallel creations बिना collisions बनें; numbering replay-safe हो।

**Source:** [backend/src/modules/alerts/infrastructure/repositories.py:185](../../backend/src/modules/alerts/infrastructure/repositories.py#L185); [backend/src/modules/alerts/application/services.py:62](../../backend/src/modules/alerts/application/services.py#L62); [backend/src/shared/database/models.py:344](../../backend/src/shared/database/models.py#L344)

### DATA-02 — Events idempotent/transactional नहीं हैं

**Priority:** P1. **Evidence:** Duplicate replay reproduced; partial-commit behavior source confirmed.

Identical event_id replay से दो violation records बने। event_id durable store नहीं होता। Violation, alert, notifications और broadcasts अलग steps/commits हैं; later failure पहले committed data छोड़ देता है और retry duplicate/inconsistent state बना सकती है।

**काम:** Inbox/event-id uniqueness + one transactional business operation + transactional outbox रखें; acknowledgement commit के बाद और recovery policy defined हो।

**Fix verify कैसे करें:** Duplicate/redelivered message से one logical violation/alert बने; failure injection के बाद restart/retry complete state recover करे।

**Source:** [backend/src/shared/messaging/consumer.py:91](../../backend/src/shared/messaging/consumer.py#L91); [backend/src/modules/ppe/infrastructure/repositories.py:43](../../backend/src/modules/ppe/infrastructure/repositories.py#L43); [backend/src/shared/database/models.py:309](../../backend/src/shared/database/models.py#L309)

### DATA-03 — Config version increment और publication atomic नहीं हैं

**Priority:** P1. **Evidence:** Reproduced concurrency; delivery failure risk source confirmed.

दो concurrent updates version 1 से दोनों version 2 बने; worker एक update stale मानकर drop कर सकता है। Database commit के बाद publish failure में config saved रहती है पर running workers stale रह सकते हैं; exclusive queue downtime में missed events recover नहीं करती।

**काम:** Optimistic locking/atomic increment + durable outbox रखें; startup/periodic full-config reconciliation करें।

**Fix verify कैसे करें:** दो successful writes distinct monotonic versions दें; broker outage और worker restart के बाद latest config लागू हो।

**Source:** [backend/src/modules/config/application/services.py:52](../../backend/src/modules/config/application/services.py#L52); [backend/src/modules/config/application/services.py:80](../../backend/src/modules/config/application/services.py#L80); [ai-worker/src/config/zone_sync.py:42](../../ai-worker/src/config/zone_sync.py#L42)

### DATA-04 — False-positive data और transition responses inconsistent हैं

**Priority:** P2. **Evidence:** Reproduced; transition race source confirmed.

Alert FalsePositive करने पर source violation.is_false_positive false रहता है, इसलिए analytics/report filtering गलत रहती है। Transition response नए resolved_on/acknowledged_on timestamps refresh नहीं करती। Concurrent transitions में expected-state guard नहीं है।

**काम:** Alert/violation state एक transaction में synchronize करें; refreshed entity लौटाएँ; state transitions conditional/versioned करें।

**Fix verify कैसे करें:** False positive compliance counts से exclude हो; response timestamps persisted values से match हों; conflicting transitions reject हों।

**Source:** [backend/src/modules/alerts/application/services.py:172](../../backend/src/modules/alerts/application/services.py#L172); [backend/src/modules/alerts/infrastructure/repositories.py:135](../../backend/src/modules/alerts/infrastructure/repositories.py#L135); [backend/src/modules/ppe/infrastructure/repositories.py:140](../../backend/src/modules/ppe/infrastructure/repositories.py#L140)

### DATA-05 — Capture/event time और factory-local shift time गलत interpret हो सकते हैं

**Priority:** P2. **Evidence:** Event-time loss reproduced; timezone gap source confirmed.

2020 event timestamp processing-time record बन गया। PPE/occupancy service body timestamp ignore करती हैं; shift tagging processing-time UTC पर होती है। Factory timezone model/config नहीं मिला, इसलिए India के local shift hours को UTC evaluate किया जा सकता है।

**काम:** Capture, emitted और ingested timestamps अलग persist करें; validated timezone per factory और late/out-of-order event handling रखें।

**Fix verify कैसे करें:** Delayed event original occurrence और local active shift से जुड़ा हो; overnight shifts अलग timezone में सही date/day use करें।

**Source:** [backend/src/modules/ppe/application/services.py:51](../../backend/src/modules/ppe/application/services.py#L51); [backend/src/modules/occupancy/application/services.py:30](../../backend/src/modules/occupancy/application/services.py#L30); [backend/src/modules/shifts/application/services.py:103](../../backend/src/modules/shifts/application/services.py#L103)

### DATA-06 — ORM और migrated schema drift; Alembic autogeneration unsafe है

**Priority:** P2. **Evidence:** Schema-aware reflection confirmed.

Fresh head database में 90 INTEGER/BIGINT width differences और 68 nullability differences मिले; missing columns zero। Alembic check failed। include_schemas absent होने से existing non-public schema tables भी additions की तरह दिखाई देती हैं; raw autogenerate output blindly apply नहीं करना चाहिए।

**काम:** Schemas-aware Alembic configuration और metadata/migrations reconciliation करें; populated-data upgrades test करें।

**Fix verify कैसे करें:** Clean head पर correct schema-aware autogeneration no unintended operations दे; existing IDs/FKs/data preserve हों।

**Source:** [backend/alembic/env.py:40](../../backend/alembic/env.py#L40); [backend/alembic/versions/0012_baseentity_int_pk_public_id.py:190](../../backend/alembic/versions/0012_baseentity_int_pk_public_id.py#L190); [backend/src/shared/database/base.py:18](../../backend/src/shared/database/base.py#L18)

### DATA-07 — Hierarchy lifecycle और input validation अधूरे हैं

**Priority:** P2. **Evidence:** Source confirmed.

Soft-deleted parent ownership lookup में deleted/status checks कई create paths पर absent हैं; children/tasks consistently deactivate नहीं होते। Factory/department/zone/camera codes, UUIDs, enums और relationships पर uniform validation/constraints नहीं हैं। Null PATCH values कई fields पर drop होती हैं, इसलिए nullable assignment clear करना संभव नहीं। Setup wizard replay progress/child relationships reset नहीं करता।

**काम:** Canonical schemas, business uniqueness, parent-state/hierarchy validation और defined clear/delete/replay semantics लागू करें।

**Fix verify कैसे करें:** Deleted parent under child-create denied हो; invalid IDs/duplicate roles/codes friendly 4xx दें; explicit null assignment clear करे; setup retry duplicate/inconsistent hierarchy न बनाए।

**Source:** [backend/src/modules/zone/application/services.py:96](../../backend/src/modules/zone/application/services.py#L96); [backend/src/modules/users/application/services.py:158](../../backend/src/modules/users/application/services.py#L158); [backend/src/modules/onboarding/application/services.py:52](../../backend/src/modules/onboarding/application/services.py#L52)

### DATA-08 — Queue delivery और notifications की recovery अधूरी है

**Priority:** P2. **Evidence:** Source confirmed.

Webhook retries और email delivery consumer callback में inline हैं; slow channels acknowledgements/live alert broadcast delay कर सकते हैं। Failed mail durable retry job नहीं बनाता। DLQ configured है, लेकिन replay tooling/retry policy नहीं मिली। Worker cooldown before snapshot/publish success mark हो सकता है, जिससे transient failure के बाद retry suppressed हो।

**काम:** Durable notification jobs/outbox, bounded retries and DLQ operator tooling रखें; delivery acknowledgement के अनुसार retry/cooldown semantics तय करें।

**Fix verify कैसे करें:** SMTP/webhook/storage/broker failure के बाद alert evidence और delivery recover हो; duplicates control हों; detection loop/outbound delays bounded रहें।

**Source:** [backend/src/modules/notifications/application/services.py:46](../../backend/src/modules/notifications/application/services.py#L46); [backend/src/shared/messaging/consumer.py:50](../../backend/src/shared/messaging/consumer.py#L50); [ai-worker/src/pipeline/ppe_validator.py:150](../../ai-worker/src/pipeline/ppe_validator.py#L150)

### DATA-09 — Audit append-only guarantee और coverage अधूरी है

**Priority:** P2. **Evidence:** Source confirmed.

Audit failure केवल log होकर swallow होती है और rollback नहीं किया जाता। Database immutability/append-only enforcement नहीं मिला। Camera CRUD, shifts और recipient operations का audit coverage consistent नहीं; correlation ID middleware/propagation absent है।

**काम:** Audit durability policy, failure transaction handling, DB permissions/tamper protection तथा complete action/correlation coverage तय करें।

**Fix verify कैसे करें:** Protected action का audit trace recoverable हो; audit write failure silent gap न छोड़े; allowed account audit rows update/delete न कर सके।

**Source:** [backend/src/modules/audit/application/services.py:64](../../backend/src/modules/audit/application/services.py#L64); [backend/src/core/app.py:20](../../backend/src/core/app.py#L20); [backend/src/modules/camera/api/routes.py:46](../../backend/src/modules/camera/api/routes.py#L46)

### SCALE-01 — Multiple backend instances में live event delivery सही नहीं होगी

**Priority:** P1. **Evidence:** Source topology confirmed.

WebSocket rooms process memory में हैं। सभी backends same RabbitMQ queue consume करते हैं; one event one consumer तक जाएगा, जबकि clients दूसरे instance से जुड़े हो सकते हैं। Redis pub/sub fanout implementation नहीं मिली।

**काम:** Separate durable processing from cross-instance live fanout; shared pub/sub/event bus और reconnect/resync protocol जोड़ें।

**Fix verify कैसे करें:** दो API replicas पर जुड़े clients relevant events receive करें; exactly-once business processing और client dedup/resync verify हों।

**Source:** [backend/src/modules/realtime/manager.py:19](../../backend/src/modules/realtime/manager.py#L19); [backend/src/shared/messaging/consumer.py:29](../../backend/src/shared/messaging/consumer.py#L29)

### SCALE-02 — Blocking report/storage operations और unbounded list/export semantics

**Priority:** P2. **Evidence:** Source confirmed; load tests unrun.

Async report endpoint में PDF/Excel build और synchronous MinIO upload हैं; event loop block हो सकता है। Report rows silently limit 5000 हैं। User listing प्रति row roles query करती है और कुछ other lists unpaginated हैं। Safety score no alerts को 100 देता है, even when detection availability unknown हो।

**काम:** Background report jobs/offloaded IO, pagination, explicit truncation/export options और availability-aware analytics रखें; measure actual queries/latency।

**Fix verify कैसे करें:** Large reports API p95 latency न बिगाड़ें; >5000 rows silently lose न हों; growing tenant data bounded responses दें; offline detection healthy score न दिखाए।

**Source:** [backend/src/modules/reports/application/services.py:69](../../backend/src/modules/reports/application/services.py#L69); [backend/src/modules/reports/application/services.py:130](../../backend/src/modules/reports/application/services.py#L130); [backend/src/modules/users/infrastructure/repositories.py:139](../../backend/src/modules/users/infrastructure/repositories.py#L139); [backend/src/modules/analytics/application/services.py:156](../../backend/src/modules/analytics/application/services.py#L156)

### DEPLOY-01 — Production overlay public ports और dev mounts retain करती है

**Priority:** P1. **Evidence:** Rendered Compose configuration confirmed.

ports: [] inherited mappings reset नहीं करती। Rendered production config ने database/cache/broker/storage/backend तथा dev frontend port retain किए। Empty volumes similarly merge behavior deserve verification।

**काम:** Supported !reset/!override semantics or independent production compose रखें; rendered config assert करें।

**Fix verify कैसे करें:** Production में only intended ingress ports और production mounts रहें; no backend reload/dev source mounts or infrastructure host exposure।

**Source:** [docker-compose.prod.yml:29](../../docker-compose.prod.yml#L29); [docker-compose.prod.yml:63](../../docker-compose.prod.yml#L63)

### DEPLOY-02 — Production frontend Dockerfile wrong build context paths use करती है

**Priority:** P1. **Evidence:** Source paths confirmed; image build unrun.

Root context selected है, लेकिन COPY package.json root से है जबकि manifest frontend/ में है। npm ci/build working directory और nginx file copy needs एक consistent context layout।

**काम:** Dockerfile COPY paths/build working directory ठीक करें और production image build CI में जोड़ें।

**Fix verify कैसे करें:** Fresh production image build सफल हो; built SPA assets तथा nginx config सही image में हों।

**Source:** [docker-compose.prod.yml:72](../../docker-compose.prod.yml#L72); [frontend/Dockerfile.prod:8](../../frontend/Dockerfile.prod#L8)

### DEPLOY-03 — Repository Docker startup migrations नहीं चलाता

**Priority:** P1. **Evidence:** Source confirmed; fresh Docker boot unrun.

Backend Docker CMD uvicorn है; init_db केवल connection verify करता है, schema readiness नहीं। Fresh compose deployment tables/migrations के बिना live health दिखा सकता है और business requests fail कर सकती हैं। Cloud setup helper migrations चलाता है, लेकिन original Docker path अलग है।

**काम:** Explicit serialized migration job/release step, readiness schema check और migration failure handling जोड़ें।

**Fix verify कैसे करें:** Empty database पर documented deploy schema head तक पहुँचे और business smoke pass करे; migration failures traffic block करें।

**Source:** [backend/Dockerfile:17](../../backend/Dockerfile#L17); [backend/src/shared/database/session.py:21](../../backend/src/shared/database/session.py#L21)

### DEPLOY-04 — TLS/public URLs और remote WebRTC configuration अधूरी है

**Priority:** P1. **Evidence:** Source confirmed; real-domain/ICE deployment unrun.

Nginx listens HTTP 80 while refresh cookie always Secure है। Storage client signing secure=False से HTTP URLs बनती हैं; default public endpoint localhost है। Optional blank WebRTC URL frontend में localhost fallback करती है; ICE additional hosts loopback हैं। Real RTSP source को viewer relay automatically नहीं करता।

**काम:** TLS ingress और public HTTPS storage/viewer routes configure करें; scoped media auth, real ICE/TURN addresses और relay provisioning दें।

**Fix verify कैसे करें:** Remote HTTPS browser login/reload/refresh, snapshots/reports और actual live stream without mixed-content/localhost dependencies काम करें।

**Source:** [infra/nginx/frontend.conf:5](../../infra/nginx/frontend.conf#L5); [backend/src/shared/storage/minio_client.py:31](../../backend/src/shared/storage/minio_client.py#L31); [frontend/src/api/client.ts:12](../../frontend/src/api/client.ts#L12); [infra/mediamtx/mediamtx.yml:15](../../infra/mediamtx/mediamtx.yml#L15)

### DEPLOY-05 — MinIO distribution/maintenance dependency अब unreliable है

**Priority:** P1. **Evidence:** Download/pull failure observed earlier; source build validated.

Official download endpoint ने 410 और community archive/no security updates notice दिया। Original image pulls unavailable थे। Current development source build restores functionality, लेकिन production maintenance/support strategy नहीं बनाता।

**काम:** Maintained S3-compatible service/storage decision लें; versioned verified artifacts, upgrade policy और restore compatibility test करें।

**Fix verify कैसे करें:** Fresh environments reliably install storage; supported patching और production durability/availability requirements documented और tested हों।

**Source:** [docker-compose.yml:58](../../docker-compose.yml#L58); [backend/src/shared/storage/minio_client.py:25](../../backend/src/shared/storage/minio_client.py#L25)

### DEPLOY-06 — Readiness केवल Redis जाँचती है; incident alerts configured नहीं हैं

**Priority:** P2. **Evidence:** Source confirmed; production health-failure injection unrun.

Database/broker/storage outage after startup readiness में capture नहीं होगी। Prometheus/Grafana starter config है, लेकिन operational alert rules, detection-staleness alarm और recovery runbooks नहीं मिले।

**काम:** Required dependencies, schema and processing freshness को readiness/status में include करें; actionable alerts और ownership/runbooks रखें।

**Fix verify कैसे करें:** Dependency failures/dead workers monitoring में visible हों; agreed detection/service SLA breach पर operators को alert मिले।

**Source:** [backend/src/modules/health/api/routes.py:14](../../backend/src/modules/health/api/routes.py#L14); [infra/prometheus/prometheus.yml:5](../../infra/prometheus/prometheus.yml#L5)

### DEPLOY-07 — Retention, backup verification और recovery guarantees absent हैं

**Priority:** P2. **Evidence:** Source confirmed; backup/restore drills unrun.

Nightly retention/archival implementation/lifecycle policy नहीं मिली। Backup scripts DB और objects sequentially copy करती हैं; consistent cut, offsite checksums, restore verification और scheduled automation absent हैं। Durable in-flight broker events backup assumptions में excluded हैं। Current source-built MinIO के लिए original Docker mc backup path भी revalidation चाहता है।

**काम:** Retention job, consistent/offsite backup, durable event recovery, explicit RPO/RTO और periodic isolated restore drills लागू करें।

**Fix verify कैसे करें:** Representative database+objects restore हों; manifests/hash checks pass हों; cleanup retention boundary preserve करे; outage data-loss window measured हो।

**Source:** [infra/backup/backup.sh:2](../../infra/backup/backup.sh#L2); [infra/backup/restore.sh:34](../../infra/backup/restore.sh#L34); [backend/src/shared/storage/minio_client.py:17](../../backend/src/shared/storage/minio_client.py#L17)

### SEC-01 — Known dependency advisories को address करना जरूरी है

**Priority:** P1. **Evidence:** Package audits executed; exploitability not proven.

Resolved backend audit: 8 affected packages, 42 returned entries with 22 unique package/advisory pairs। Frontend npm audit: 10 affected package entries, 6 high + 4 moderate। Declared AI direct requirements audit: python-dotenv affected; heavy inference transitive stack not installed/audited here।

**काम:** Fixable runtime advisories prioritize करें; compatibility-tested controlled upgrades/lock or constraints रखें; upstream no-fix advisories assess करें; automated audit CI जोड़ें।

**Fix verify कैसे करें:** Reviewed advisories resolved/justified हों और updated auth/API/inference/browser regression suites pass करें; auto force-fix न करें।

**Source:** [backend/requirements.txt:16](../../backend/requirements.txt#L16); [frontend/package.json:17](../../frontend/package.json#L17); [ai-worker/requirements.txt:2](../../ai-worker/requirements.txt#L2)

### UI-01 — Alerts/violations pagination और dashboard counts गलत scale होते हैं

**Priority:** P2. **Evidence:** Source confirmed; browser E2E unrun.

Lists केवल first 100 rows fetch करती हैं। Open alert count returned array length है, total/aggregate नहीं; >100 alerts undercount होते हैं। Activity invalidation feedEvents.length पर निर्भर है; capped length पर new events trigger नहीं करते। Live occupancy latest single event है, enterprise/zone aggregate और stale state नहीं।

**काम:** Server aggregate counters और real pagination; latest event identifier/version invalidation; per-zone freshness/aggregation रखें।

**Fix verify कैसे करें:** 101+ alerts सही total दिखाएँ; old records accessible हों; full activity buffer पर new events UI update करें; disconnected/stale occupancy explicit हो।

**Source:** [frontend/src/pages/Dashboard.tsx:27](../../frontend/src/pages/Dashboard.tsx#L27); [frontend/src/pages/Dashboard.tsx:71](../../frontend/src/pages/Dashboard.tsx#L71); [frontend/src/pages/Alerts.tsx:19](../../frontend/src/pages/Alerts.tsx#L19); [frontend/src/pages/Violations.tsx:25](../../frontend/src/pages/Violations.tsx#L25)

### UI-02 — WebSocket cleanup और session UI state असंगत है

**Priority:** P2. **Evidence:** Source confirmed; browser behavior unrun.

Reconnect timers clear नहीं होते और connect entry पर cancelled check नहीं है; cleanup के बाद timer socket खोल सकता है। AppShell और Dashboard independent sockets रखते हैं। Token refresh existing persisted user/roles को reuse करती है। Several mutation controls roles/errors consistently handle नहीं करते।

**काम:** Shared socket lifecycle, timer cancellation, latest /auth/me profile and role-aware controls/error/empty/loading states रखें।

**Fix verify कैसे करें:** Logout/unmount पर no orphan sockets; token expiry/reconnect tests pass हों; changed user roles UI में refresh हों; failures invisible empty-success न लगें।

**Source:** [frontend/src/hooks/useWebSocket.ts:50](../../frontend/src/hooks/useWebSocket.ts#L50); [frontend/src/api/client.ts:41](../../frontend/src/api/client.ts#L41); [frontend/src/pages/LiveGrid.tsx:50](../../frontend/src/pages/LiveGrid.tsx#L50)

### PRODUCT-01 — Advertised capability और delivered UI/logic में gaps हैं

**Priority:** P2. **Evidence:** API/router/code inventory confirmed.

Routes/sidebar में full reports, analytics, shifts, maintenance, notification settings, setup wizard और password-change screens नहीं मिले। Dynamic catalog recognition नहीं देता। Generic rule engine/unauthorized-zone-entry detection, model hot-swap, escalation, MFA तथा full recording/employee identity capability current path में implemented नहीं मिलीं। README ByteTrack/zero polling/no-code 200-camera scale claims current code से मेल नहीं खाते।

**काम:** Implemented/planned/unsupported capability matrix publish करें; actual required workflows prioritize करें; unsupported options disable/label करें।

**Fix verify कैसे करें:** हर promised feature का real API/UI/model/smoke evidence हो; exact employee identification, real PPE detection और recording claims actual capability से match हों।

**Source:** [frontend/src/router.tsx:22](../../frontend/src/router.tsx#L22); [ai-worker/src/pipeline/person_tracker.py:55](../../ai-worker/src/pipeline/person_tracker.py#L55); [README.md:570](../../README.md#L570)

### QUALITY-01 — Passing unit tests production behavior cover नहीं करतीं

**Priority:** P2. **Evidence:** Existing suites/build/lint executed earlier; targeted checks this review.

21 backend tests + 25 AI tests passed earlier; backend coverage 16% थी। Existing CI lint two unused imports पर fail करती है। No configured frontend browser suite; cross-tenant, concurrent, remote-outage, event replay, migration upgrades, TLS/streaming, restore and load tests absent/unrun हैं।

**काम:** Risk-based integration/browser/concurrency/fault tests, production image/config checks और real-camera acceptance suite CI/pilot gate बनाएं।

**Fix verify कैसे करें:** Critical findings fixed with regressions; green CI, fresh deploy and realistic fault/load/model tests pass हों; 200 cameras बिना measured evidence claim न करें।

**Source:** [.github/workflows/ci.yml:29](../../.github/workflows/ci.yml#L29); [backend/tests/test_security.py:9](../../backend/tests/test_security.py#L9); [frontend/package.json:6](../../frontend/package.json#L6)

## क्या पहले करना चाहिए

1. **Tenant/authorization boundary:** AUTH-01 through AUTH-10. Centralized scope enforcement और malicious/mismatched reference regression checks पहले रखें; maintenance suppression तथा streaming को भी इसमें शामिल करें।
2. **Safety/event correctness:** AI-01 through AI-07, DATA-01 through DATA-04. Demo isolation, frame-voting/config correctness, review-event persistence, atomic numbering/idempotency और concurrency fix करें।
3. **Deployability:** DEPLOY-01 through DEPLOY-06 और SEC-01. Production config/image, migrations, TLS/public URLs, maintained storage तथा reviewed dependency upgrades के साथ fresh deployment verify करें।
4. **Operational pilot:** Camera lifecycle/recovery, person evidence, occupancy/time semantics, durable notification delivery, audit and backup/retention पूरा करें।
5. **Product/load acceptance:** UI pagination/session behavior, missing promised workflows, real PPE holdout validation और progressively larger camera-load tests करें; तब multiple API/GPU workers scale करें।

पहले architecture को microservices में rewrite करने की आवश्यकता नहीं है। Existing module boundaries बनाए रखकर security, contracts, transactions और lifecycle defects ठीक करें। Multi-instance WebSocket delivery के लिए implementation change आवश्यक है; केवल replicas बढ़ाना पर्याप्त नहीं।

## Production release gate

- Two-tenant / two-factory / zone-scoped-role permission matrix: no unauthorized read, mutation, stream or notification delivery.
- Logout/suspend/revoke/password-change/role-change and concurrent refresh: old sessions invalidated and rotating tokens truly single-use.
- Missing or unsupported PPE model cannot silently produce real-looking compliance records; per-class model accuracy and false alerts measured on held-out target-factory footage.
- Positive/clean/positive frame sequences, empty PPE requirements, shoes/mask capabilities, stale/hot config and camera overrides have regression checks.
- Duplicate/out-of-order messages, broker/storage/API outages and process restarts produce recoverable, consistent event/alert/evidence state.
- Production rendered Compose, image builds, empty-DB boot, TLS cookies, public signed downloads and authenticated remote WebRTC have smoke tests.
- Camera offline/failover, stale telemetry and dependency failure visible; alert delivery and backup/restore meet explicit operational targets.
- Real load measured for target camera resolution/sample rate/model: inference latency, capture-to-alert latency, frame age, GPU memory, dropped frames, queue depth, API p95 and DB/storage growth.
- Relevant critical findings resolved, package advisories reviewed and CI green; documented requirements/feature claims match demonstrated behavior.

## Dependency audit details

Frontend audit affected packages: axios, baseline-browser-mapping, browserslist, esbuild, nanoid, postcss, react-router, react-router-dom, source-map-js and vite. npm severity breakdown: 6 high, 4 moderate. Some updates require a major tooling upgrade; force-fix should not substitute compatibility testing.

Resolved backend affected packages: aiosmtplib, ecdsa, orjson, pytest, python-dotenv, python-jose, python-multipart and starlette. Tool returned 42 advisory entries, including duplicates; there are 22 unique package/advisory pairs. Dev-tool and runtime exposure should be assessed separately; advisory matches are not proof of exploited or exploitable behavior.

Declared AI direct requirements audit found python-dotenv advisories. This does not establish the safety of ultralytics → torch or the complete heavy inference environment, which was not installed for this review.

**Correction to an earlier setup statement:** NumPy 1.26.4 remains a tested development pin matching the AI requirements. OpenCV 4.10 also imported successfully with an isolated NumPy 2.5.4 install. A mandatory OpenCV/NumPy-2 incompatibility was not demonstrated; it is not a confirmed defect in this report. The saved startup note was corrected.

## Evidence artifacts

- [Backend reproduction results](evidence/2026-10-12/visionguard-deep-backend-results.json)
- [AI reproduction results](evidence/2026-10-12/visionguard-deep-ai-results.json)
- [Concurrency/protocol reproduction results](evidence/2026-10-12/visionguard-deep-extra-results.json)
- [Schema-aware drift details](evidence/2026-10-12/visionguard-schema-drift.json)
- Alembic check failed. Its raw autogenerated diff is not included because missing schema-aware discovery produces false table additions; use the schema-aware drift evidence instead.
- [Frontend npm audit](evidence/2026-10-12/visionguard-npm-audit.json)
- [Resolved backend package audit](evidence/2026-10-12/visionguard-python-resolved-audit.json)
- [Declared AI direct package audit](evidence/2026-10-12/visionguard-ai-deps-audit.json)
- [Source/config inventory](evidence/2026-10-12/visionguard-review-inventory.json)
- [Machine-readable findings](evidence/2026-10-12/visionguard-deep-findings.json)

## Reproduction checklist

| Check | Undesired behavior reproduced | Observation |
|---|---|---|
| AUTH-SCOPE-FACTORY | True | Factory manager reads a different factory in same enterprise; HTTP 200 |
| AUTH-SCOPE-FACTORY-WRITE | True | Factory manager updates another factory; HTTP 200 |
| AUTH-SCOPE-CONFIG | True | Factory manager reads another factory zone config; HTTP 200 |
| AUTH-SCOPE-MAINTENANCE | True | Factory manager suppresses another factory camera alerts; HTTP 200 |
| AUTH-SCOPE-CAMERA-CREATE | True | Factory manager creates camera in another factory; HTTP 200 |
| AUTH-INACTIVE-TOKEN | True | Existing access token still accepted after database account suspension; HTTP 200 |
| DATA-CROSS-TENANT-DEPARTMENT | True | Department in tenant A accepted factory foreign key belonging to tenant B |
| DATA-CROSS-TENANT-NOTIFY | True | Tenant A zone recipient accepted a tenant B user; no notification sent by this probe |
| DATA-CROSS-TENANT-SHIFT | True | Tenant A shift accepted tenant B factory |
| ALERT-NUMBER-TENANTS | True | Second tenant first alert fails global alert_number uniqueness: IntegrityError |
| EVENT-DUPLICATE | True | Replaying identical event_id creates 2 violation records |
| EVENT-TIMESTAMP | True | 2020 event timestamp persisted as processing time instead |
| ALERT-TRANSITION-RESPONSE | True | FalsePositive response lacks newly written resolved_on timestamp |
| FALSE-POSITIVE-DATA | True | FalsePositive alert leaves source violation is_false_positive=false |
| LOW-CONFIDENCE-DROPPED | True | Low-confidence review event creates no review record |
| AI-NONCONSECUTIVE-VOTING | True | Positive/clean/positive/clean/positive emitted violation despite no three consecutive positive frames |
| AI-EMPTY-PPE | True | Explicitly empty PPE requirements still emit helmet violation |
| AI-SHOES-THRESHOLD | True | 0.80 shoes violation emitted with configured shoes_threshold=0.99 |
| AI-TRACK-ID-DROPPED | True | Confirmed violation output omits person track_id |
| AI-CONFIG-VERSION | True | Worker initial config_version=5 accepts stale hot-update version=2 |
| AI-CONFIG-CONTRACT | True | Hot config replaces ppe_required with required_ppe_types; validator reads former key |
| AI-MASK-UNSUPPORTED | True | Mask violation is not mapped to any event in validator |
| AUTH-REFRESH-RACE | True | One rotating refresh token produced 2 successful concurrent refresh responses |
| CAMERA-URL-PROTOCOL | True | Viewer can use RTSP test endpoint to read a local JPEG path rather than an RTSP URL; HTTP 200 |
| CONFIG-CONCURRENT-VERSION | True | Two concurrent updates: starting version 1, final version 2, returned versions [2, 2] |

Development setup persistence/publication and application production readiness remain separate. Existing install/start instructions are saved; publication/fresh-task restoration was not established by this review.
