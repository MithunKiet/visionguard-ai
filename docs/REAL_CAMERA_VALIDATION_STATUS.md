# Real-camera validation status — 2026-10-14

**Actual-camera validation is pending required inputs.** The user confirmed an authorized reachable RTSP camera exists, but its environment-variable name/location has not yet been provided. Inspection found no configured RTSP validation variable, AI-worker environment file, local PPE checkpoint or labeled real-camera dataset in this checkout. The local development camera registry contains only a simulator/test source. The available test environment has OpenCV; it does not currently have the full torch/Ultralytics inference runtime or an exposed NVIDIA device.

## Completed preparation

- Added a bounded, non-recording RTSP probe and held-out frame evaluator using the application's actual detector/preprocessing, with demo and remote fallback disabled.
- Added strict label/manifest checks and per-class/per-condition counts, precision and recall. Missing class coverage is explicitly unmeasured. Reports never grant production approval.
- Added a manifest template and [site-validation instructions](REAL_CAMERA_VALIDATION.md), including safe data collection, target-hardware testing, event-level metrics and physical-camera placement evidence.
- All 48 AI tests passed, including 16 validation-runner regressions; configured AI lint passed. Evaluator integration tests use a fake detector to check report calculation and input handling; they do not validate a real model.
- A local **synthetic** MediaMTX smoke decoded 71 frames at 640×360 from a 15 FPS test-pattern source during a roughly three-second probe. No read failure occurred and no footage was saved. Decode throughput was about 23 FPS because buffered frames can drain faster than capture; this does not establish camera FPS, latency or detection accuracy.

## Inputs still needed

1. The environment-variable name holding the authorized RTSP connection, securely configured on a machine with the correct camera-network route.
2. A trusted compatible PPE checkpoint location and the target inference environment/hardware.
3. Independently labeled, held-out footage/frames with camera/session/condition metadata and site-agreed acceptance targets.

No real-camera accuracy, detection distance, missed-event rate, false-alert rate, GPU capacity or production readiness is claimed. Actual RTSP probing can start as soon as the connection setting is supplied; accuracy evaluation additionally requires the model and labels.
