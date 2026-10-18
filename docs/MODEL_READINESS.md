# Verified model and GPU startup

P4 removes silent CPU fallback and configuration-derived GPU reporting. A production worker registers, fetches assignments and starts camera tasks only after its local model passes the startup checks below. P4 originally used schema `0019`; the current deployment requires `0020` for P5 ownership fencing. The existing heartbeat API is retained.

## Startup contract

1. `ENVIRONMENT=production` requires `USE_GPU=true`, `DEMO_MODE=false`, a local PPE checkpoint and its reviewed expected `YOLO_MODEL_SHA256`. Missing weights cannot switch production to a hosted provider or COCO/demo model.
2. The worker computes SHA-256 and checks the expected digest **before loading the checkpoint**. Obtain that expected value from a trusted, reviewed artifact source. A hash computed from an unknown download does not make PyTorch deserialization safe. Keep production models mounted read-only.
3. Requested CUDA must be available and expose at least one device. The worker selects `cuda:0` inside its container; Docker's explicit GPU assignment determines which host GPU is visible there. Explicit CPU operation remains available in development and offline validation, and reports `gpu_available=false`.
4. The loaded model must have task `detect` and exactly this class mapping: `helmet`, `no_helmet`, `vest`, `no_vest`, `gloves`, `no_gloves`, `safety_shoes`, `no_safety_shoes`, `person`, at indices 0–8. The six-class webcam trial model is incompatible. This contract adds no mask detector.
5. The worker moves the model to the selected device, preprocesses and infers a blank 640×640 BGR image, parses the result, checks model/predictor/backend device placement and synchronizes CUDA to catch deferred launch errors. Every later inference explicitly supplies the same device.

Loading and warmup run on the dedicated inference executor, leaving the event loop and P2 delivery retries available during normal startup. No camera is opened and no operational alert is emitted by warmup. In development-only remote mode, warmup can call the configured provider with the blank image; production disallows that fallback.

## Runtime reporting and failure behavior

HTTP and broker heartbeats use the detector's verified fields, never the current `USE_GPU` setting. `gpu_available` means this ready model/predictor uses CUDA, not merely that CUDA was requested or the host has a GPU. `model_version` now contains `<mode>:<first 40 SHA-256 characters>`, fitting the existing 50-character column. Full SHA-256 is retained in startup logs and the readiness report. Modes are `ppe`, `remote` and `demo`; the latter two are development modes.

A model execution exception or observed device mismatch revokes readiness. Further inference is rejected until restart, and a ready heartbeat is not sent. A currently executing native batch older than `MODEL_STALL_SECONDS` (default 30, range 1–600) also fails the readiness check. The main loop stops camera tasks and closes publisher state when it observes a readiness failure. Queue overload and expired frames alone do not revoke model readiness.

Readiness is evaluated at startup, registration, assignment reconciliation and heartbeat cadence, normally every 30 seconds plus API time. It is not instantaneous failure detection or hardware attestation; the backend trusts the authenticated worker's report. A last successful heartbeat remains historical data until the backend's existing timeout. It does not grant new factory/capacity permissions.

Native PyTorch/CUDA initialization or inference can hang beyond Python cancellation. The worker does not safely kill a GPU thread or guarantee process exit in that case; thread cleanup can remain blocked. Use the bounded preflight below and a tested external process/container supervisor for forced recovery. Compose's restart policy alone does not restart a process that stays alive but is hung. P5 implements lease-based camera takeover; see [WORKER_FAILOVER.md](WORKER_FAILOVER.md) for its conditions and the remaining site failure drills.

## Deploy and run the preflight

Production Compose now requires `PPE_MODEL_SHA256` and maps it to the worker's `YOLO_MODEL_SHA256`. Set `PPE_MODEL_PATH` to the model path inside the worker (default `models/yolov8s-ppe.pt`). Both supplied workers use the same reviewed artifact; their GPU identities remain separately configured. `MODEL_STALL_SECONDS` must exceed the measured acceptable native batch duration. Do not raise it to hide sustained overload.

Rebuild worker images and run the preflight in the **same image/inference environment and GPU allocation** that will serve the pilot, without competing production inference load:

```sh
cd ai-worker
python -m src.validation.model_readiness \
  --weights models/yolov8s-ppe.pt \
  --model-sha256 EXPECTED_REVIEWED_SHA256 \
  --device cuda --timeout-seconds 120 \
  --output ../validation-results/gpu-readiness.json
```

Use a new report path each run. The parent process bounds the probe, writes `model_ready`, `model_readiness_failed` or `model_readiness_timeout`, and returns nonzero on failure. Reports omit raw native errors that may expose local paths or credentials. A successful report records actual device, GPU name, artifact identity, classes and package versions; `production_approved` always stays `false`. CPU comparisons use `--device cpu` and cannot establish GPU readiness. Capture driver/container versions separately with your deployment evidence.

Then recreate workers while preserving their P2 state volumes. Verify `vg_model_ready=1`, `vg_model_cuda_active=1`, the digest-based registry identity and fresh per-camera results. Prometheus includes a model-not-ready rule; worker metrics unavailability is covered by the existing rule. Configure and test operations notification delivery separately.

## Evidence and remaining gates

Local verification on 2026-10-16:

- Main AI suite: 156 passed; native RTSP and actual CPU-model smoke were skipped in that environment. Existing real RabbitMQ and pinned trial ONNX checks ran.
- Actual CPU smoke ran separately and passed using PyTorch `2.5.1+cpu`, torchvision `0.20.1+cpu`, Ultralytics `8.3.50`, NumPy `1.26.4` and OpenCV `4.10.0`. It generated an **untrained, test-only** nine-class checkpoint locally, verified loading/warmup/reporting through the actual CLI, and verified that requesting CUDA on that CPU runner fails. No test checkpoint was promoted to production weights. CI now has a separate CPU smoke job.
- Policy tests cover missing CUDA/devices, driver errors, missing/wrong pin, missing production weights despite remote credentials, exact classes/task, wrong model/predictor device, warmup and asynchronous CUDA errors, runtime readiness loss, truthful heartbeats, cleanup, executor startup and probe timeout/report preservation.
- 23 PostgreSQL integration tests passed for scheduling, heartbeat identity/device round trips and durable replay. Configured lint, production Compose validation and Prometheus semantic rules passed. Existing backend dependency deprecation warnings remain.

No target GPU or reviewed production PPE weights are available here. The full GPU image/dependency stack, CUDA kernel compatibility on the chosen host, model accuracy, batch capacity and failure recovery remain deployment acceptance gates. A blank-image warmup proves execution, not PPE accuracy or a safe camera count. Continue with [measured sizing](PRODUCTION_CAPACITY.md) and the [persistent remediation plan](MULTI_FACTORY_REMEDIATION.md).
