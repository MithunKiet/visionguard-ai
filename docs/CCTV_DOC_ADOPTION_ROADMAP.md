# CCTV Analytics document — adoption roadmap

Modules from the company "CCTV Analytics — Technical Architecture & Implementation
Plan" document that VisionGuard AI does not have yet, or has only in part.

**Rule:** before implementing anything, check this file first. When an item is
finished, change its status, add the date, the PR link and the doc that
describes it. Do not mark an item Done on synthetic tests alone when its
acceptance needs real cameras; use "Built, not site-validated" instead.

Status values: `Not started` · `In progress` · `Built, not site-validated` · `Done` · `Dropped`

## Summary

| # | Module | Priority | Status |
|---|---|---|---|
| 1 | Asset Monitoring Phase A (reference-photo change monitoring) | — | Built, not site-validated (PR #7, #8) |
| 2 | Restricted-area (no-entry zone) monitoring | High | Not started |
| 3 | Asset Monitoring Phase B (extinguisher detection model) | High | Not started |
| 4 | AI model registry and versions (UI + rollback) | Medium | Not started |
| 5 | Monitoring schedules per rule and per asset | Medium | Not started |
| 6 | Evidence and event retention policies | Medium | Not started |
| 7 | Storage capacity alerts | Medium | Not started |
| 8 | One camera covering several zones | Low | Not started |
| 9 | Safety goggles PPE class | Low | Not started |
| 10 | GPU optimization (TensorRT / DeepStream) | Low until benchmarked | Not started |
| 11 | Per-use-case accuracy targets and acceptance | High (gate) | Tooling ready, data pending |

## Already in VisionGuard (no work needed)

These document items already exist, so they are not tracked above:
alert cooldown/deduplication, per-zone notification recipients, `model_version`
on violations, PPE-to-person tracking, camera connection test, dynamic config
without restart, durable event retry, acknowledgement/closure, audit trail,
worker health, reports.

## Details

### 1. Asset Monitoring Phase A
- **Document:** UC-02 fire extinguisher monitoring, individual asset records, ROI, history.
- **What exists:** migration 0027, Asset Monitoring page, asset types, reference capture, ROI, "area changed" / "view changed" alerts. See `docs/FIRE_EXTINGUISHER_MONITORING.md`.
- **Remaining:** real-camera false-alarm measurement. Marked Done only after a site test.

### 2. Restricted-area (no-entry zone) monitoring
- **Document:** UC-03. Draw polygon zones on a camera, alert when a person enters or stays, time-based rules (e.g. allowed only during a shift, or nobody after 10 PM).
- **Why:** it is one of the document's three confirmed use cases and VisionGuard has nothing for it. The person detector and tracker already exist, so no new model is needed.
- **Likely scope:** polygon editor (similar to `RoiEditor`), per-camera restricted areas, dwell-time and schedule rules in the worker, new alert type, zone-policy delivery like assets.
- **Acceptance:** real-camera entry events, false-alarm rate measured on site.

### 3. Asset Monitoring Phase B
- **Document:** detect missing, displaced and obstructed extinguishers.
- **What it needs:** labeled factory images of extinguishers, a trained detection model, and a separate model contract (the current PPE runtime requires the exact nine-class mapping).
- **Blocked on:** labeled data. See `docs/PPE_MODEL_SELECTION.md` for the training rules.

### 4. AI model registry and versions
- **Document:** model master, version history, approve before production, rollback, assign a model to a camera.
- **What exists:** checksum/warmup startup guards (`docs/MODEL_READINESS.md`), `model_version` on violations.
- **Missing:** a registry table and UI, approval state, rollback, per-camera model assignment.

### 5. Monitoring schedules per rule and per asset
- **Document:** a schedule on every rule (24×7 or time windows), per asset too.
- **What exists:** shifts and maintenance mode.
- **Missing:** "run this rule only between these hours" for PPE, assets and restricted areas.

### 6. Evidence and event retention policies
- **Document:** retention and archival for images and events.
- **Missing:** configurable retention (e.g. delete snapshots after N days), archival, storage cleanup job. Must respect backups and open incidents.

### 7. Storage capacity alerts
- **Document:** disk storage capacity alerts.
- **Missing:** alert when MinIO / database disk crosses a threshold (could be a Prometheus/Grafana rule).

### 8. One camera covering several zones
- **Document:** a camera may cover several locations, and a location may have several cameras.
- **What exists:** each camera belongs to one zone.
- **Note:** this is an architecture change (camera-to-zone mapping). Needs a proposal and approval before any work.

### 9. Safety goggles PPE class
- **Document:** goggles where visible.
- **Blocked on:** a model that detects goggles. The runtime class mapping must change deliberately; do not relabel an existing class.

### 10. GPU optimization (TensorRT / DeepStream)
- **Document:** hardware decode, TensorRT engines, batching for 30 cameras.
- **First:** run `benchmark-gpu-windows.cmd` on real hardware. Only optimize if measured capacity is not enough. See `docs/WINDOWS_GPU.md`.

### 11. Per-use-case accuracy targets
- **Document:** separate precision, recall and false-alarm targets per use case, validated on annotated factory footage.
- **What exists:** `evaluate-ppe-windows.cmd`, `docs/PPE_ACCURACY_EVALUATION.md`, public baseline.
- **Blocked on:** labeled factory data. This is the gate before calling anything production-ready.

## Change log

| Date | Item | Change | PR |
|---|---|---|---|
| 2026-11-03 | — | File created from the document comparison | — |
