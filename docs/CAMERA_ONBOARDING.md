# Camera onboarding and bulk import

Flow 7 registers cameras in manageable batches and keeps them out of worker admission until an operator activates them. DVR/NVR recording remains independent. Registration, receiving one frame and fresh PPE inference are three separate checks.

## Operator workflow

1. Create the factory and zones. Open **Cameras → Import CSV** as a system administrator, enterprise administrator or factory manager. Managers can import only into their current authorized factory/zone scope.
2. Download the header template and use **Available zone IDs** to find public UUIDs. Required columns: `name,code,zone_id,rtsp_url`. Optional columns: `factory_id,fps,camera_type,position_desc`.
3. Fill a private UTF-8 CSV with at most 200 cameras. The complete JSON request must fit 512 KiB, including encoding overhead. Quote CSV fields containing commas. Keep camera passwords out of tickets and source control. Use only authorized hosts accepted by the server's RTSP host policy.
4. Preview and fix every error. Factory IDs, when supplied, must match each zone. FPS must be finite and between 0.1 and 30; blank inherits existing configuration behavior. Camera types are `Fixed`, `PTZ` or `Fisheye`. Codes use ASCII letters, digits, dot, underscore or hyphen and start with a letter or digit.
5. Import within ten minutes. The batch commits completely or rolls back completely. Imported cameras have `status=Inactive`, `is_active=false` and no worker assignment. Import does not start camera readers or alerts.
6. Test each saved connection. A successful test means one frame was received from the API host; it does not prove worker network access, stable streaming or PPE accuracy. Activate selected cameras when ready. Worker polling admits eligible cameras only when factory capacity is available.
7. Open **Detection health** to confirm worker ownership, applied configuration and recent inference. Add further batches only after measuring site capacity and checking detection gaps.

The camera list displays 50 rows per page but still fetches the existing complete scoped inventory API. This is UI pagination, not a server-side large-inventory optimization. Connection checks are explicit and limited to two concurrent subprocesses per API event loop, each with a 12-second parent timeout. Every child is terminated/reaped after timeout or cancellation. Multiple API replicas each have their own limit. Checks do not persist frames or claim operational health from an old result.

## API and retry contract

- `POST /api/v1/cameras/import/preview`: JSON `csv_text`. Returns row errors, non-secret mapping information and a signed ten-minute `preview_token` only for a valid batch. It writes no cameras.
- `POST /api/v1/cameras/import/commit`: JSON `csv_text`, `preview_token`, UUID `request_key`. Rechecks current access, active locations and inventory. A preview is bound to the actor, enterprise and exact input.
- On a lost response or 5xx, retry the **same request key and CSV**. A committed receipt returns the original camera IDs with `replayed=true`, even when its preview token expired. Receipts are actor-bound and require continued visibility of every imported camera. Different input/actor with an existing key is rejected.
- The browser retains the retry key in dialog memory. Closing/reloading loses it; previewing the same CSV then flags already registered cameras. Inspect inventory before changing codes or URLs. The browser does not persist the credential-bearing CSV in local storage.
- Cameras, receipt and `CAMERAS_IMPORTED` audit entry share one transaction. Preview/receipt/audit omit RTSP URLs. Existing camera records remain the credential storage location; this flow does not introduce encryption for that existing column.

A PostgreSQL transaction advisory lock serializes normal creation, camera URL edits and bulk imports per enterprise. Codes are compared case-insensitively. Stream identity compares scheme, host, effective port, path and query while excluding user/password; different DVR channel queries remain different streams. DNS aliases, different URL encodings and tokenized query aliases can still refer to the same physical stream. This is a registration duplicate guard, not camera hardware identification. Direct database writers bypass it. Legacy duplicates are not rewritten.

## Deployment and boundaries

Apply `alembic upgrade head` from `backend` before deploying the API. Schema/readiness head is **0026** (`camera_imports`). Deploy compatible API replicas together, then the frontend. Downgrading 0026 drops retry receipts without deleting imported cameras; do not downgrade while clients may retry imports.

Imports require the same authentication and scope controls as other camera management actions. Inactive factory/zone mappings are rejected. The saved-camera health endpoint now requires a camera-management role because it actively connects to a stream. Editing a camera without changing its redacted URL preserves stored credentials, and its connection test uses the saved camera ID.

Local tests cover actual PostgreSQL transactions, concurrent duplicate imports/replay, scopes, invalid/oversized input, rollback, 200-row batches and worker admission. Probe tests launch real disposable child processes but do not connect to factory cameras. Browser tests use mocked APIs. Real factory connectivity, model accuracy, GPU sizing, provider/TLS behavior and P7 acceptance remain pending; this feature does not approve a 200/1000-camera deployment.
