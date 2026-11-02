# Asset Monitoring (Phase A, fire extinguisher first)

Migration **0027** adds per-asset records and model-free change monitoring on
cameras that already run PPE detection. The UI calls this **Asset Monitoring**
(`/asset-monitoring`; the old `/safety-assets` route redirects there).

Monitoring does not depend on the asset type. It checks whether a fixed asset
is still in its proper place. `asset_type` labels the asset and its alerts and
is one of a fixed list: `FIRE_EXTINGUISHER` (the API default, for earlier
clients), `DUSTBIN`, `FIRST_AID_BOX`, `EMERGENCY_EXIT_SIGN` or `OTHER`. The list
lives in `backend/src/modules/assets/api/schemas.py` and
`frontend/src/components/assetTypes.ts`; keep both in sync. Adding a type needs
no migration.

The API path (`/api/v1/safety-assets`), the tables and the alert types
(`SAFETY_ASSET_*`) keep their original names for compatibility. The rest of
this document uses the fire extinguisher as the example asset.

## What it detects — and what it does not

The worker compares each extinguisher's marked area (ROI) with a reference
photo. It reports **"the area no longer looks like its reference"**. It cannot
tell whether the extinguisher is missing, moved or blocked. A person reviews
the evidence photo and confirms on site.

No accuracy has been measured on real factory footage. Lighting changes, glare,
shadows, reflective surfaces and PTZ/moving cameras can cause false alerts.
Phase B (a separate extinguisher detection model trained on labeled factory
images) is required to classify missing, displaced and obstructed reliably.
Do not present Phase A as an extinguisher detector.

## Setup flow

1. **Asset Monitoring → Add asset.** Choose the asset type and the camera that
   sees it, then enter a code (unique per enterprise among live assets, e.g.
   `FE-001` or `DB-001`).
2. **Capture from camera.** The API reads one frame through the same disposable,
   12-second, two-per-event-loop child used for connection probes. Credentials
   travel on stdin only. The JPEG (≤1920 px wide) is stored privately in the
   snapshots bucket under `{enterprise}/assets/{asset}/reference/{uuid}.jpg` and
   is served only through the API, with a SHA-256 recheck.
3. **Mark the area.** Drag a box around the extinguisher, or type percentages.
   The ROI is normalized (0–1) to the reference frame.
4. **Turn monitoring on.** The API refuses until a reference and ROI exist.
5. The asset shows **Not confirmed by a worker** until a worker reports a check
   (`last_checked_at` newer than `max(3 × interval, 180 s)`).

Asset edits use optimistic `version` checks. Managing assets requires
SYSTEM_ADMIN, ENTERPRISE_ADMIN or FACTORY_MANAGER. Deleting an asset requires an
enterprise-level admin. Factory and zone visibility follows `scope.py`.

## Policy delivery

Fingerprints (32×32 ROI and a 32×18 scene thumbnail, grayscale, base64) are
computed by the API from the reference. They travel inside the existing
versioned zone policy (`config.deliveries`, migration 0021):

- Any change that affects monitoring (ROI, reference, thresholds, on/off,
  delete) bumps the zone config version and writes the history and outbox row
  in the same transaction as the asset change.
- **Every** zone policy delivery, including PPE threshold saves, carries the
  zone's complete monitored-asset list. A worker replaces its whole config on
  apply, so omitting assets would silently stop monitoring.
- Pushes carry the whole zone; the worker HTTP assignment carries each camera's
  slice. The worker filters to its own camera, so both paths compare equal.

`backend/src/modules/assets/domain/fingerprint.py` and
`ai-worker/src/pipeline/asset_fingerprint.py` must stay byte-identical. A backend
test enforces this.

## Worker behavior

`AssetMonitor` runs on frames the camera already samples, at each asset's
`check_interval_seconds`. It adds no extra inference and reuses the frame's
person boxes.

| Observation | Meaning | Effect |
|---|---|---|
| OK | ROI similarity ≥ threshold | Resets the change timer; two OKs after an incident publish `asset_restored` |
| Changed | ROI similarity below threshold | Starts/advances the change timer |
| ViewChanged | Scene (excluding the ROI) similarity < 0.5 | Separate timer and alert; never reported as a missing asset |
| Occluded | A person box covers ≥10% of the ROI | Holds every timer; no alert |

An event fires only after the same observation persists for
`change_after_seconds` **and** at least three observations. Incidents
(`asset_area_changed`, `asset_view_changed`) are durable edge-journal routes
with full-frame evidence. `asset_restored` is durable without evidence.
`asset_status_updated` is bounded telemetry. Timers survive a policy re-apply
when the asset's entry is unchanged.

A paused, lease-less, stale or disconnected camera produces no observations.
An asset therefore turns *Not confirmed*; it is never reported as present.

## Backend events

- Incidents are claimed through `event_receipts`, fenced with the historical
  lease rule, checked against the asset's camera, zone, factory and enterprise,
  and the evidence key must sit under that camera's prefix.
- At most one Open or Acknowledged alert exists per asset and kind:
  `SAFETY_ASSET_AREA_CHANGED` (High) or `SAFETY_ASSET_VIEW_CHANGED` (Medium).
  Repeat incidents attach to it. Maintenance records the incident without an
  alert.
- `asset_restored` clears open incidents but **does not close the alert**. A
  human still reviews and resolves it.
- Status telemetry uses the current-lease fence and never moves an asset's
  last observation backwards in time.
- Alert detail includes `safety_asset` with its latest incident. Evidence
  downloads go through `/safety-assets/{asset}/incidents/{incident}/snapshot`.

## Rollout

Upgrade the API (migration 0027) before the workers. Old workers ignore the
`assets` policy key, so assets stay *Not confirmed*; this is truthful, not a
failure. New workers sending asset events to an old API produce
unhandled-route warnings only.

## Validation status

- Automated: worker state machine and fingerprint tests on synthetic frames;
  backend unit tests. API/consumer integration tests exist but need the
  disposable PostgreSQL/Redis environment.
- Not done: real-camera reference capture through the API, real lighting/day–night
  behavior, false-alarm rate, and any extinguisher accuracy claim.
