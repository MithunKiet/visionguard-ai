# Incident review

Open **Alerts**, filter by status/severity, and choose **Review** beside an incident. The panel shows the factory, zone, camera, creation time, SLA deadline, linked violation snapshot and model confidence, followed by the recorded status history. Confidence is a model score, not confirmation that the incident occurred.

An authorized reviewer can acknowledge an open incident or save a final decision:

- **Resolve incident:** enter what you checked and the corrective action/outcome. The dashboard requires a nonblank note, up to 2,000 characters.
- **Mark as false positive:** explain why the detection was incorrect. The reason must be nonblank and at most 200 characters, matching the existing violation storage limit.

The API trims submitted notes/reasons and rejects blank or oversized values. For compatibility, existing API callers may still omit a resolution note when there is no corrective plan. Planned actions require completion and a closure note before resolution. Acknowledgment does not clear a violation's pending review flag. Resolution and false-positive decisions clear that flag; false-positive decisions also persist the reason and false-positive marker. The linked violation update and status history use the existing transaction. The corrective-action follow-up requires migration 0024; see [CORRECTIVE_ACTIONS.md](CORRECTIVE_ACTIONS.md).

## Permissions and evidence

System administrators, enterprise administrators, factory managers and safety officers can save decisions within their existing location scope. Other users can inspect incidents available to them but do not see review controls. API checks enforce the role, enterprise and factory/zone scope independently of the UI. History returns public IDs and reviewer names within the incident's enterprise; unavailable names are shown as such.

Snapshots use the existing scoped violation endpoint and expiring storage URLs. No snapshot is created by opening a review. Missing, expired or inaccessible evidence is shown explicitly. **Refresh evidence** requests fresh incident details and evidence. If incident access is rejected, the panel removes cached details, the image and decision controls. A previously issued presigned image URL retains its existing expiry behavior; this change does not add immediate revocation to object storage.

The panel refreshes incident status every 15 seconds. Save failures retain draft text while the current status is reloaded; a concurrent final decision is shown instead of silently overwriting it. Status transitions serialize with corrective-plan changes and retain transition checks. Completed incident decisions cannot be reopened or edited through this panel. Review history now also includes assignment, corrective plans, photo attachments and action-completion notes.

## Scope and validation

This workflow reviews existing alerts. Low-confidence violations that intentionally generate no alert remain in the violations list; a separate adjudication queue for those items is not included. This change does not train a model, establish camera accuracy, add recorded video/audio, or alter alert delivery.

Backend integration checks use a migrated disposable PostgreSQL database and Redis to verify role/location access, history, normalized notes, pending-review flags and competing final decisions. Browser tests exercise evidence display, required notes, false-positive reasons, read-only access, failed saves, concurrent updates and revoked access. Build and regression results are recorded in the change summary.

Local validation on 2026-10-14: 92 backend tests passed in the full run, followed by one additional passing concurrent-decision integration test. The optional synthetic MediaMTX smoke was skipped because no test relay URL was configured. All 15 browser tests passed; the seven incident-review browser tests passed again after the final pagination adjustment. Backend lint and the frontend type-check/production build passed. Browser tests use mocked API responses; database-backed tests separately exercise actual API persistence and authorization.
