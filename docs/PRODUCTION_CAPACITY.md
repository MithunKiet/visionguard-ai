# Production preparation and measured sizing

**No production camera-per-GPU capacity has been established.** The production hardware is not selected, compatible nine-class production weights and representative site data have not been supplied, and a real-camera end-to-end soak has not run. The laptop capture report and six-class webcam trial do not establish factory capacity or production-model accuracy. This workflow prepares repeatable measurements and conservative candidate plans; it does not certify deployment.

## Compare candidate hardware

Choose a representative camera profile first: resolution, codec/bitrate, actual capture FPS, configured detection sample FPS, lighting, scene density, required PPE, number of concurrent live viewers, alert bursts and retention. Keep it identical across candidate machines. Use the intended model and exact image/package versions; changing the model, GPU sharing, resolution or scene density invalidates a sizing comparison.

Record CPU model/core count, RAM, GPU model/VRAM, CUDA/driver versions, disk throughput/free space, network interfaces, host identity and build revision. NVIDIA CUDA support is needed for the GPU deployment image; the inference benchmark also accepts CPU for comparison. There is no justified universal minimum specification yet. Choose memory/disk/network from measured demand and the retention budget below.

Start with one worker on one GPU. The production overlay now requires `WORKER_1_GPU_DEVICE_ID` and `WORKER_2_GPU_DEVICE_ID`, removes development source/log mounts from workers, and mounts `/app/models` read-only plus a distinct writable persistent `/app/state` volume for each worker. Preserve those volumes across recreation; see [DURABLE_EDGE_EVENTS.md](DURABLE_EDGE_EVENTS.md) for the local journal, bounded cached assignments and replay/recovery procedures. Worker application files are baked into the image; rebuilding/recreating the worker is required after code changes. Collect stdout centrally before replacing containers because the development log bind mounts are removed. Use GPU UUIDs or stable device IDs. Assigning two workers to the same GPU is allowed by Docker but must be tested as a combined workload; an individual-worker benchmark cannot justify that sharing. The provided Compose topology defines two fixed worker identities, not automatic GPU discovery or autoscaling. Both defined GPU assignments must be configured when rendering it.

Validate the GPU image build and CUDA startup on the candidate host using the [bounded model-readiness preflight](MODEL_READINESS.md). Production now requires `PPE_MODEL_SHA256`, local nine-class weights and verified CUDA warmup; it will not silently use CPU or remote/demo fallback. The existing full GPU dependency stack/image has not been rebuilt or certified by this change. Keep CPU fallback out of GPU capacity comparisons: the benchmark fails if CUDA was requested but unavailable. Supply worker tenant credentials, trusted camera networks, maintained object storage and real production secrets as described in [REVIEW_FIXES.md](REVIEW_FIXES.md) and [SECURE_LIVE_VIDEO.md](SECURE_LIVE_VIDEO.md).

## 1. Measure inference on the actual candidate

Use a trusted local checkpoint compatible with the production nine-class detector. Do not substitute the experimental six-class webcam ONNX model. Obtain its expected SHA-256 from your reviewed model artifact. PyTorch checkpoint loading requires trusting that artifact, not merely computing a hash of an unknown download.

Place 1–16 representative, authorized still images under the ignored `capacity-data/` directory. Include crowded scenes and relevant camera resolutions. Create `capacity-data/frames.json` with relative paths:

```json
{"images": ["images/day-crowded.jpg", "images/dim-occluded.jpg"]}
```

From `ai-worker/`, using the same inference environment that will run the worker:

```sh
python -m src.capacity.benchmark \
  --weights models/yolov8s-ppe.pt --model-sha256 EXPECTED_SHA256 \
  --manifest ../capacity-data/frames.json --device cuda \
  --cameras 1 2 4 8 12 --fps 2 --seconds 120 \
  --p95-ms 500 --min-fps-ratio 0.95 \
  --output ../capacity-results/inference-candidate-a.json
```

The benchmark warms up the production detector, then submits synchronized camera-equivalent work to the actual batch queue, with one outstanding request per simulated camera. It records per-camera achieved FPS, missed schedule slots, failures and request p95, plus model/image hashes, package/device identity and GPU peak allocated memory. The allocator peak excludes reserved memory and other processes; measure whole-device use separately during the pilot. Completion after the observation window is reported separately and does not inflate throughput. Each level passes only when **every** camera meets the supplied rate/latency target with zero errors. These example targets are starting criteria to agree before testing, not universal safety requirements.

It never opens cameras, publishes events, sends notifications or uploads images. It deliberately excludes decode, network buffering, tracking/voting, snapshots, broker/database work and video viewers. Repeated still images cannot validate live-camera freshness or accuracy. The highest passing level is only an **inference-only tested level**, not a deployment camera count, maximum capacity, or proof of spare capacity. Run repeated trials and preserve every report; do not retain only the best run.

Requests use `DETECTION_QUEUE_SIZE` (default 32 waiting frames, plus up to 8 in flight) and `DETECTION_TIMEOUT_SECONDS` (default 5 seconds). Overflow is rejected, cancelled/expired queued frames are skipped, malformed batch output fails every affected request, and requests have deadlines. Inference failures break consecutive-frame voting while preserving alert cooldowns. Native model execution cannot be interrupted by an asyncio timeout; a hung model still requires process restart. The benchmark parent enforces an overall process deadline. P3 live cameras also impose `FRAME_MAX_AGE_SECONDS` (default 2 seconds) from local decode, check it at inference entry/result and reject results after connection/configuration changes. Capture drains continuously in a separate process per camera with latest-frame replacement; inference has its own executor. See [CAPTURE_ISOLATION.md](CAPTURE_ISOLATION.md) for default 1080p slot limits and shared-memory configuration. Do not increase queue size to conceal falling FPS. Measure parent plus capture-child CPU/RAM, decoder buffers and shared slots; upstream camera/DVR lag remains outside the local timestamp. Inference-only benchmarks exclude these capture processes.

## 2. Measure the combined camera workload

Install a small authorized pilot and increase load gradually, for example 2, 4, then 8 cameras, stopping as soon as a target is missed. Stay below the inference-only passing level. Run the full worker/backend/storage/broker/media stack together, with the expected number of live viewers and reviewers. Test quiet scenes, busy scenes, lighting changes, intended PPE, notification bursts, reconnects and an impaired stream. Keep notification recipients confined to your authorized test destination.

Maintain representative database volume. For read-only API load, run the supplied k6 script against the authorized staging origin, with a short-lived scoped user token in environment settings:

```sh
# Set CAPACITY_BASE_URL and CAPACITY_ACCESS_TOKEN in the secure environment.
CAPACITY_EXPECTED_CAMERAS=1000 CAPACITY_READ_CYCLES_PER_SECOND=2 CAPACITY_DURATION=10m k6 run \
  --summary-export capacity-results/api-candidate-a.json infra/capacity/api-load.js
```

The script issues two scheduled read cycles per second by default, each reading alerts, violations and cameras. It checks successful populated responses, per-route p95 < 750 ms and zero dropped iterations. Set the expected camera count and minimum persisted alert/violation history; see [FLEET_MONITORING.md](FLEET_MONITORING.md) for fleet discovery and repeatable synthetic control-plane measurements. It does not measure writes, WebSocket fanout, HLS bandwidth or notifications. Exercise those separately with authorized accounts and destinations. Never publish token values or enable HTTP header debug logging. A healthy empty database and a mocked test server are not representative capacity evidence.

Monitor these worker signals in Prometheus, retaining raw samples and report timestamps:

| Signal | What to inspect |
| --- | --- |
| `rate(vg_frames_processed_total[5m])` / `vg_camera_target_fps` | Each camera's achieved sampling rate; aggregate FPS can hide starvation. |
| `vg_frames_discarded_total`, `vg_capture_restarts_total`, `vg_frame_local_age_seconds` | Separate normal latest-slot replacement from stale results; inspect stalled/invalid captures and local age. |
| `vg_model_ready`, `vg_model_cuda_active` | Observed model/predictor readiness and CUDA use; a successful startup is not accuracy or capacity evidence. |
| `vg_detection_queue_depth` | Current waiting frames. A bounded or empty queue alone does not establish health. |
| `vg_detection_failures_total` | Inspect `overload`, `timeout` and `inference` reasons separately; zero failures is required for a candidate pass. |
| `vg_frame_processing_seconds` | Submit-to-result latency, including failures/timeouts; not capture-to-alert latency. |
| `vg_inference_batch_seconds`, `vg_batch_size` | Batch service time and batching efficiency. |
| `vg_camera_last_processed_timestamp_seconds` | Stalled inference even when a stream still appears connected. |
| `vg_edge_pending`, `vg_edge_pending_bytes`, `vg_edge_oldest_age_seconds`, `vg_edge_rejected_total` | Incident/evidence backlog, age and rejected local writes; size disk for measured outage bursts. |
| `vg_edge_assignment_cache_active`, `vg_edge_delivery_failures_total` | Cached authorization use and independent delivery failures. |
| `process_resident_memory_bytes`, whole-container/process-tree CPU/RAM/GPU monitoring | Parent process metrics exclude capture children. Measure all child/decoder/shared-buffer resource use and add host/GPU exporters. |

The new Prometheus rules detect unreachable workers, inference failures, stale results, low per-camera FPS, unavailable model readiness, high request p95, rejected local incidents, aged edge backlog and sustained cached-assignment use. Defaults are advisory and must be tuned to the approved pilot. Prometheus evaluates these rules, but this repository does not configure Alertmanager delivery; connect and test your operations notification path before relying on pages. Worker targets use file discovery generated from a validated operator inventory. Production requires `FLEET_TARGETS_DIR`; run the registry/Prometheus coverage audit after changes and on a schedule, as described in [FLEET_MONITORING.md](FLEET_MONITORING.md). GPU utilization/VRAM, disk/network saturation, RabbitMQ queue age/depth and notification outbox age still require their corresponding monitoring/exporters.

A locally fresh decode timestamp cannot prove source freshness or detect a camera repeatedly sending a frozen scene. Measure capture-to-alert p95 using synchronized clocks and controlled visible events correlated with persisted alerts. A worker's inference timer does not include camera/network buffering, and processed-frame counts cannot prove frame freshness. Record stale frames, lost events, provider failures and false/missed detections. Video and evidence availability must be tested on the actual HTTPS deployment.

Run at least a 24-hour soak covering representative operating conditions, then repeat at a reduced sustainable load with reserve capacity. Test a worker/GPU outage and recovery. The scheduler now enforces administrator-configured factory boundaries and camera budgets, and fills unassigned cameras when capacity becomes available; see [WORKER_SCHEDULING.md](WORKER_SCHEDULING.md) for migration 0019 and required configuration. A budget must come from measurement. P5 now supports automatic takeover of expired leased cameras by a ready same-factory standby with spare measured capacity. See [WORKER_FAILOVER.md](WORKER_FAILOVER.md) for schema 0020, the mandatory coordinated upgrade, bounded offline authorization and site RTO/fencing limitations. Workers retain distinct identities; a stale heartbeat alone never authorizes takeover. Admission budgets do not prove hardware capacity.

## 3. Turn measured pilot evidence into a candidate plan

Copy `infra/capacity/pilot.example.json` into `capacity-data/` and fill it from retained measurements. Its nulls are intentional: the unfilled template must fail. The report describes **one worker's** measured workload on a specified hardware profile, with every camera measured simultaneously under the combined system load. Reference the source telemetry, exact settings, build and tested viewer/alert rates in `evidence_reference`. Do not enter inference-only benchmark numbers as live-camera results.

```sh
python infra/capacity/plan.py \
  --evidence capacity-data/pilot-candidate-a.json --target-cameras 20 \
  --headroom 0.30 --spare-workers 1 --min-hours 24 --max-p95-seconds 10 \
  --output capacity-results/plan-candidate-a.json
```

The default policy requires zero measured losses, stale-frame events, notification failures and inference errors; every camera at >=95% of target FPS; capture-to-alert p95 <=10 seconds; CPU/RAM/GPU-memory peaks <=85%; the combined components exercised; and a completed failover drill. Adjust latency/soak targets deliberately before collecting evidence. The tool checks the submitted values but cannot independently establish that the measurements or labels are correct. All output retains `production_approved=false`.

Sizing uses:

```text
planned cameras per worker = floor(measured stable cameras per worker × (1 − headroom))
active workers            = ceil(target cameras / planned cameras per worker)
total workers             = active workers + failure reserve
```

For illustration only: 10 measured stable cameras, 30% headroom and a target of 20 would produce 7 planned cameras per worker, 3 active workers and 1 standby. **These are not measured VisionGuard capacity results.** The spare must have equivalent capacity and a tested activation path. Mixed camera profiles or heterogeneous GPUs need separate workload pools and measurements. The planner must not multiply a one-worker result indefinitely: retest shared database/broker/storage/network/media capacity at the intended total load.

## Production release gates

Before enabling unattended operation, retain evidence for:

- Accuracy on independent site labels, camera placement/occlusion tests, and reviewed model/data licensing. Sizing does not establish accuracy.
- Production secrets, TLS, private infrastructure/media access, tenant-scoped worker credentials, trusted camera egress and production configuration validation. Run `python infra/check_production_config.py`; it checks topology with test placeholders, not your real secrets, certificates or host readiness.
- Reproducible GPU image build, CUDA/model startup, pinned artifact checksums, dependency/image scanning and rollback rehearsal on the candidate hardware.
- Authenticated live playback, API/database/broker/storage stress and actual provider delivery. Per-process database connection allowance is currently 10 pooled + 20 overflow; budget all API processes, migrations and administration below the database connection limit before adding replicas.
- Retention and storage budgets: snapshot bytes/day = measured average JPEG bytes × daily saved snapshots. Continuous video recording is not implemented. If separately introduced, decimal GB/day per stream is approximately bitrate_Mbps × 10.8, before replication/overhead. Add retention, replicas and backup headroom; measure network traffic for ingest, HLS viewers and uploads together.
- Scheduled encrypted offsite backups and an isolated database/object restore drill with agreed RPO/RTO. Existing backup scripts alone do not establish recovery. Broker messages not yet persisted as application events cannot be assumed recoverable from PostgreSQL; plan broker durability/draining and verify losses explicitly. P2 retains local incidents until broker confirmation and evidence upload, not until backend consumption. Worker state volumes are outside the existing backup script; preserve them and test replay after restart and controlled migration.
- Tested operations alerts, response ownership, rollback thresholds, spare capacity and a controlled rollout. This Compose installation remains a single-host topology; worker reserve alone does not make the database, broker, storage or ingress highly available.

## Evidence from this workspace

The new queue, timeout, batch-result handling, per-camera benchmark scoring and planner gates are tested with controlled fixtures. The production Compose topology and Prometheus rules are checked without deploying services. No candidate GPU, compatible production checkpoint, representative real RTSP workload, sustained production API benchmark or production restore drill has been measured here. P6 synthetic control-plane measurements are recorded separately in the remediation plan and must not be interpreted as video inference capacity. Keep the camera-per-worker capacity **unknown** until those measurements exist.

Local validation on 2026-10-14: 42 AI tests and 17 sizing-policy tests passed; configured lint, worker runtime imports (without loading weights), production Compose checks, Prometheus configuration/rule checks and rule-evaluation tests passed. The k6 script passed a syntax check; it has not been load-tested against a deployment. The unfilled pilot template produced `insufficient_evidence` with no worker-count recommendation. These checks validate tooling, not production throughput.
