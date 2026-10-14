# Real-camera validation status — 2026-10-14

**Actual-camera validation is pending a local webcam test and model/data inputs.** The user clarified that the available device is a Windows laptop webcam. The cloud workspace cannot access that device. A Windows launcher and local preview/probe are now available; the laptop's measurement report has not been received. The local cloud camera registry contains only a simulator/test source. No compatible PPE checkpoint or labeled dataset is installed here; the cloud environment also lacks the full torch/Ultralytics inference runtime and an exposed NVIDIA device.

## Completed preparation

- Added a bounded, non-recording RTSP probe and held-out frame evaluator using the application's actual detector/preprocessing, with demo and remote fallback disabled.
- Added strict label/manifest checks and per-class/per-condition counts, precision and recall. Missing class coverage is explicitly unmeasured. Reports never grant production approval.
- Added a manifest template and [site-validation instructions](REAL_CAMERA_VALIDATION.md), including safe data collection, target-hardware testing, event-level metrics and physical-camera placement evidence.
- All 55 AI tests passed locally, including 16 validation-runner and seven webcam regressions; configured AI lint passed. Webcam tests mock the camera driver; neither Windows launcher execution nor a physical laptop camera has been verified here. A Windows CI job was added, but its remote result has not been verified. Evaluator integration tests use a fake detector to check report calculation and input handling; they do not validate a real model.
- A local **synthetic** MediaMTX smoke decoded 71 frames at 640×360 from a 15 FPS test-pattern source during a roughly three-second probe. No read failure occurred and no footage was saved. Decode throughput was about 23 FPS because buffered frames can drain faster than capture; this does not establish camera FPS, latency or detection accuracy.

## Inputs still needed

1. A measurement report from `check-webcam-windows.cmd` on the Windows laptop (see [WINDOWS_WEBCAM.md](WINDOWS_WEBCAM.md)). RTSP settings are unnecessary for this webcam check.
2. A trusted compatible PPE checkpoint location and the target inference environment/hardware.
3. Independently labeled, held-out footage/frames with camera/session/condition metadata and site-agreed acceptance targets.

No real-camera accuracy, detection distance, missed-event rate, false-alert rate, GPU capacity or production readiness is claimed. The webcam probe can run locally now; accuracy evaluation additionally requires the model and labels. Factory RTSP validation remains a later site-specific step.
