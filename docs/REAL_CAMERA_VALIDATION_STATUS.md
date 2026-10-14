# Real-camera validation status — 2026-10-14

**Windows webcam capture passed; PPE accuracy remains unmeasured.** The submitted report records 899 frames over 30 seconds at 1280×720, approximately 29.95 decoded FPS, no read failures and a maximum inter-frame gap of 0.125 seconds. No footage was saved. These are capture measurements, not detection results. The cloud workspace cannot access the laptop webcam.

## Completed preparation

- Added a bounded, non-recording RTSP probe and held-out frame evaluator using the application's actual detector/preprocessing, with demo and remote fallback disabled.
- Added strict label/manifest checks and per-class/per-condition counts, precision and recall. Missing class coverage is explicitly unmeasured. Reports never grant production approval.
- Added a manifest template and [site-validation instructions](REAL_CAMERA_VALIDATION.md), including safe data collection, target-hardware testing, event-level metrics and physical-camera placement evidence.
- Added the Windows capture launcher and a separate [local PPE webcam trial](PPE_WEBCAM_TRIAL.md). The trial downloads a checksum-pinned public six-class ONNX model and displays CPU predictions locally without recording, uploading frames or sending alerts. It does not replace the production nine-class detector.
- All 63 AI tests passed locally, including the optional actual ONNX inference smoke. Configured AI lint passed. Webcam driver/GUI tests use mocks; physical Windows execution of the new PPE trial remains pending. Windows CI coverage includes the trial regressions, but its remote result has not been verified. Production evaluator integration tests use a fake detector to check report calculation and input handling, not real-model accuracy.
- The pinned ONNX model loaded and ran on this cloud CPU. A blank frame produced no detections. The publisher's already-annotated demo image produced one helmet, two person and two vest boxes at confidence 0.5 (about 257 ms inference including preprocessing/postprocessing in this one run). This image is not independent labeled evidence; this smoke establishes executable inference only and does not validate missed violations or accuracy.
- A local **synthetic** MediaMTX smoke decoded 71 frames at 640×360 from a 15 FPS test-pattern source during a roughly three-second probe. No read failure occurred and no footage was saved. Decode throughput was about 23 FPS because buffered frames can drain faster than capture; this does not establish camera FPS, latency or detection accuracy.

## Inputs still needed

1. Run `test-ppe-windows.cmd` on the laptop and review the local predictions (see [PPE_WEBCAM_TRIAL.md](PPE_WEBCAM_TRIAL.md)). Share its statistics report and observations of obvious correct/missed/incorrect predictions. RTSP settings are unnecessary for this webcam trial.
2. For production evaluation, supply a trusted checkpoint compatible with the application's nine-class detector and identify the target inference hardware. The public six-class ONNX trial is a separate experiment; it cannot directly use the production evaluator or worker configuration. No compatible production checkpoint is installed here.
3. Independently labeled, held-out footage/frames with camera/session/condition metadata and site-agreed acceptance targets. Observing a preview alone does not measure accuracy.

No real-camera PPE accuracy, detection distance, missed-event rate, false-alert rate, GPU capacity or production readiness is claimed. Factory RTSP validation remains a later site-specific step.
