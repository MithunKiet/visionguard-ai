# Capture isolation and local frame freshness

P3 separates live camera capture from inference and local incident acceptance. Each assigned camera has one spawned OpenCV capture process, one shared raw-frame slot and one latest-frame slot in the parent worker. The child continuously drains the stream while the parent handles inference or persists evidence. A slow consumer replaces pending frames instead of building a historical FIFO. DVR/NVR recording is unchanged.

## Runtime behavior

- OpenCV open, read, property access and release run in the child, outside the shared asyncio thread pool. Children load no PPE model. OpenCV preprocessing and FFmpeg decoding each use one thread per capture process.
- Sampling uses elapsed host monotonic time. Changing the zone sample FPS updates the running child without reconnecting. Inactive cameras still drain their feeds, but do not submit inference; their resource cost still counts toward the scheduling budget.
- The parent polls without waiting on the shared lock. A native call or abandoned lock cannot hold the parent event loop indefinitely. No progress triggers termination, followed by kill if needed; the old child must be reaped before replacement. Reconnect backoff is 5, 15, then 60 seconds, resetting after a sustained connection. Linux children also request termination when their parent dies.
- Generator closure and camera task cancellation explicitly stop the supervisor and reap its child. Assignment removals cancel all affected camera tasks before waiting for cleanup, so termination deadlines are paid concurrently.
- Inference remains batched and serial in a dedicated executor thread, separate from journal/JPEG/object-store work. The queue and actual inference entry both check deadlines. A native GPU call still cannot be killed by a Python timeout; a hung model requires worker/process recovery. This change does not implement GPU process supervision or distributed ownership fencing.

## What the age limit means

Each sample carries host monotonic time and wall time recorded **after OpenCV finishes decoding it**. The worker checks that local age before inference, after inference and before handing each incident to durable acceptance. The earlier of the detection timeout and the frame freshness deadline applies. Expired queued frames are skipped; late results do not update voting, occupancy or violations. A gap clears consecutive-frame votes while retaining existing delivery cooldowns.

Results from a prior connection generation or superseded active/configuration state are also rejected. Accepted PPE/occupancy/overcrowding events use the observation's local decode wall time, preserving it through P2 replay. Once a valid incident is handed to durable acceptance, encoding, disk writes and network retries can take longer than the frame budget; historical accepted incidents must still be delivered.

This is **not a camera exposure timestamp or proof of end-to-end freshness**. Camera/NVR encoding delay, RTSP buffers, decoder delay and a source replaying old video remain upstream of this timestamp. A frozen image repeatedly sent with new packets can look locally fresh. Validate actual source-to-alert age with synchronized clocks and visible timed events at the site. No camera-source timestamp mapping or frozen-scene classifier was added. Sustained decode below source FPS can still accumulate upstream lag; use a suitable camera substream and measure it.

## Settings and deployment

| Setting | Default | Meaning |
| --- | --- | --- |
| `FRAME_MAX_AGE_SECONDS` | `2` | Maximum local decode-to-inference/result age, range 0.1–60 seconds |
| `CAPTURE_STALL_SECONDS` | `15` | No-progress watchdog, including process/open startup; range 1–120 seconds |
| `CAPTURE_STOP_TIMEOUT_SECONDS` | `1` | Wait after terminate and again after kill; range 0.1–10 seconds |
| `CAPTURE_MAX_FRAME_BYTES` | `6220800` | Shared slot size: 1920 × 1080 × 3 bytes, maximum configured value 96 MiB |
| `WORKER_SHM_SIZE` | `256m` | Compose shared-memory allowance per worker |

The OpenCV backend is explicitly FFmpeg, with 10-second open/read hints and one decoder thread. The parent watchdog is the fallback when native calls ignore those hints. Start through `python -m src.main` or the worker container so Python spawn has an importable entry point. The production worker is Linux; Windows laptop trial scripts are separate and unchanged.

Rebuild/recreate workers to deploy; schema remains `0019`. Preserve P2 state volumes. The default raw slot accepts up to 1080p BGR frames. A larger or invalid frame is rejected and the capture retries with `invalid_frame`; it is never silently resized. For 3840 × 2160 BGR, set `CAPTURE_MAX_FRAME_BYTES=24883200` and provision corresponding shared memory/RAM before restarting.

Re-measure capacity after this upgrade. Capture now drains and decodes streams continuously, so CPU/network demand can rise compared with an inference-blocked reader. Each camera adds a Python/OpenCV process, decoder buffers, a shared slot, parent frame copies and its current inference image. The slot budget is not a cap on the whole process or native decoder allocation. Size shared memory from at least `assigned cameras × CAPTURE_MAX_FRAME_BYTES` plus allocator headroom; Python shared arenas may fall back to temporary storage when shared memory is insufficient. Check `/dev/shm`, temporary storage, process limits and the entire container/process-tree RSS/CPU, not only the parent Prometheus process metrics. A larger shared-memory allowance is not preallocated camera capacity.

An OS process stuck in uninterruptible kernel I/O may require host intervention even after kill; software deadlines do not guarantee the OS can reap it. No automatic cross-host takeover is added. P4 now supplies [verified startup/runtime guards](MODEL_READINESS.md), with actual target-GPU acceptance still pending. P5 fenced failover remains separate work.

## Monitoring and verification

- `vg_capture_last_received_timestamp_seconds`: last sampled local decode wall time.
- `vg_capture_restarts_total{reason="stalled"|"exited"|"invalid_frame"}`: capture recovery and invalid frame counts.
- `vg_frames_discarded_total{reason=...}`: `superseded` means the latest slot replaced an unconsumed sample; `stale_*`, `policy_changed` and `stream_changed` identify rejected frames/results. Ordinary superseding is expected under a slower consumer and is not itself a stale-result alert.
- `vg_frame_local_age_seconds`: local decode-to-return age, excluding upstream delay. Existing processed-frame counters now count fresh results accepted by the camera pipeline.

Prometheus rules cover repeated capture restarts and stale discards. Keep per-camera FPS/stall alerts and the P2 delivery alerts. Alertmanager delivery still needs deployment configuration.

Verified locally on 2026-10-15:

- 131 AI tests passed, including real spawned children stuck in open/read/release, a child holding the shared lock, healthy-camera progress during another camera's recovery, latest-frame replacement, FPS hot changes, oversized frame rejection, cancellation cleanup, concurrent assignment removal, stale/config-displaced results and inference isolation from a busy default executor.
- A native OpenCV/FFmpeg smoke consumed a generated 320 × 240, 20 FPS RTSP stream from local MediaMTX 1.12.3 with a deliberately slow consumer. It verified recent local decode timestamps and process cleanup. Real RabbitMQ delivery checks and the pinned trial ONNX smoke also ran in the AI suite.
- The PostgreSQL durable replay regression passed, retaining one incident/alert for a replayed event. Configured lint, production Compose checks and Prometheus semantic rule tests passed.

The synthetic stream is not a factory camera, production model accuracy result or capacity benchmark. No real DVR/GPU/200-camera soak or camera-origin timestamp validation ran. The full production GPU image was not rebuilt here. Optional RTSP regression: set `TEST_CAPTURE_RTSP_URL` securely to an authorized test stream and run `pytest tests/test_capture_isolation.py`; do not put camera credentials in logs or commands.

See [the persistent remediation plan](MULTI_FACTORY_REMEDIATION.md) and [measured capacity workflow](PRODUCTION_CAPACITY.md) for the remaining rollout gates.
