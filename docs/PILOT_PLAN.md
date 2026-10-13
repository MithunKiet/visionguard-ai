# Small camera pilot

Start with 2–4 cameras in one factory, with a named site owner and reviewer. This is a validation plan, not evidence that the system is production-ready. The remaining engineering gaps are tracked in [REVIEW_FIXES.md](REVIEW_FIXES.md).

## Preparation

Record the camera models, resolution, lens/field of view, mounting height, distance to each observation area, network path, lighting and operating shifts. Select the PPE classes the supplied model actually supports. Define acceptable missed-event and false-alert rates, alert latency, recovery time and data retention with the site owner before testing; no universal accuracy or cameras-per-GPU claim is assumed.

Use a separate pilot tenant and isolated camera network. Configure unique worker credentials, trusted camera hosts, HTTPS, storage access and backup/restore procedures. Keep public live playback disabled until the tenant-authorized media gateway is implemented. Use a controlled test recipient for notifications; verify durable delivery and retries before relying on alerts operationally.

## Camera placement and detection evaluation

1. Start with a representative camera and several marked distances within its field of view. Record object size in pixels, mounting angle, lighting, motion blur and occlusion at each point. Distance alone cannot establish detection quality.
2. Collect authorized, representative examples of compliant and non-compliant PPE use without exposing participants to hazards. Label ground truth independently of model predictions. Include different shifts, people, clothing and crowded scenes.
3. Evaluate held-out footage, keeping tuning footage separate. Report precision, recall, false alerts per camera-hour and missed events for each PPE class and operating condition, with sample counts and uncertainty.
4. Choose the usable observation area from measured results. Repeat after changing the lens, resolution, camera position or model. Camera-local track IDs do not establish employee identity.

## Reliability and capacity

Verify camera off/on controls, first login, session expiry/logout, tenant isolation, event review, report downloads and configured alert delivery. Disconnect and reconnect each camera, restart a worker, and interrupt broker/storage connectivity in the isolated pilot. Record lost or duplicate events, recovery time and whether operators see accurate camera status.

Increase from one camera to the planned pilot count. Measure capture-to-alert latency (including p95), processed/dropped frames, queue backlog, CPU/GPU utilization, GPU memory, network bandwidth and storage growth across a representative shift. Camera count alone is insufficient: resolution, sample rate, model, scene density and hardware all affect capacity. Use these measurements to choose headroom and a camera-per-worker limit.

## Exit evidence

Keep an English pilot report containing:

- Hardware/software versions, model identity, camera placement and all effective detection settings.
- Labeled sample counts and per-class/condition accuracy results against the agreed targets.
- Latency, throughput, resource use and recovery observations.
- Notification and backup-restore results, open defects and assigned owners.
- A decision to expand, retest or stop, based on the agreed targets.

A pilot requires actual camera access, model weights, site-approved footage and target hardware. Those physical tests have not been run in the cloud workspace. Audio recording is unnecessary for the current visual PPE pipeline. Continuous archival, incident video clips, violence detection and named-person identification require separate implementation and validation.
