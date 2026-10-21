# Check the laptop CUDA runtime

The owner reported an NVIDIA RTX 2000 Ada Generation Laptop GPU, 8,188 MiB VRAM and driver 595.95 through `nvidia-smi`. This is a candidate for local development and measurement, not a measured factory camera budget. The cloud workspace cannot access this laptop's GPU; run the following check on the laptop.

## Run on Windows

1. Connect laptop power, use a ventilated surface and close heavy GPU applications. Keep normal company security controls enabled.
2. Install 64-bit Python 3.11 with its Python launcher if it is not already present. The existing webcam runner also uses Python 3.11.
3. Pull the latest repository or extract a fresh ZIP. From its root, double-click **`check-gpu-windows.cmd`**. In Command Prompt, the equivalent is:

   ```bat
   git pull origin main
   check-gpu-windows.cmd
   ```

4. The first run creates `.venv-gpu` and installs `torch==2.6.0+cu124` from the official PyTorch CUDA 12.4 wheel index. This is a large download and needs free disk space and internet access. The Windows Python 3.11 wheel was confirmed in the official index. No administrator access, standalone CUDA Toolkit or webcam-environment modification is required for this probe. The NVIDIA driver must work with the bundled runtime; actual execution below is the check.
5. After installation, a child process has a 90-second deadline to initialize CUDA, warm up and perform ten small 1024×1024 FP32 matrix multiplications on `cuda:0`. It synchronizes CUDA and verifies the numerical result. There is no CPU fallback. The deadline covers the probe, not dependency download/install.
6. Share the printed `validation-results\gpu-check-<id>.json` report. Successful status is **`cuda_compute_verified`**. It includes GPU name, total/free VRAM, PyTorch/CUDA versions, compute capability and the small computation timing. It contains no camera URLs, images, host/user names or credentials.

The probe does not load/download a model, access a camera/microphone, upload data, run a worker or send alerts. Existing webcam scripts still use their separate CPU ONNX environment; this check does not switch them to GPU. A successful matrix operation is not a PPE result, performance benchmark, thermal soak or deployment-image certification. `production_approved`, `accuracy_validated` and `camera_capacity_measured` remain false.

## Troubleshooting and next step

- `cuda_unavailable`: retain the report and run `nvidia-smi` again. Check that the script used `.venv-gpu`; a CPU-only PyTorch environment does not establish CUDA support. Do not silently change this check to CPU.
- `runtime_error`: share the report's error type. Check available GPU memory and the NVIDIA driver through the approved driver/IT process. Native error text is intentionally omitted from the JSON because it can include private paths.
- `probe_timeout`: initialization/computation did not finish within the bound. Close competing GPU workloads, restart the laptop if appropriate and retry with a new report. Do not accept a timeout as readiness.
- Dependency installation failure: inspect the displayed pip error, available disk space and access to `download.pytorch.org`. Preserve TLS verification. Download/install requires internet, but the CUDA computation itself uses no network.

Once CUDA computation passes, provide a trusted production nine-class PPE checkpoint and its reviewed SHA-256. Use the full detector environment and [model-readiness preflight](MODEL_READINESS.md), followed by [real-camera evaluation](REAL_CAMERA_VALIDATION.md) and [measured capacity](PRODUCTION_CAPACITY.md). The standalone probe environment intentionally contains only PyTorch; it is not the full worker installation. Model/device execution and camera count must be remeasured in the actual inference environment. The existing six-class webcam ONNX trial cannot substitute for those production weights.

Do not use the matrix timing to estimate cameras per GPU. Decode, model size, sample FPS, tracking, scene density, laptop power/thermal limits, other GPU applications and shared services determine that result. Real factory access, representative labels and integrated testing remain necessary for [P7 acceptance](FACTORY_PILOT_ACCEPTANCE.md).

## Run the GPU inference load sweep on Windows

The repository now includes `benchmark-gpu-windows.cmd`. This is the next measurement after CUDA readiness, not a live-camera capacity certification. It requires:

- A **trusted production nine-class `.pt` PPE checkpoint** accepted by `PPEDetector`, and its independently reviewed SHA-256. The six-class webcam ONNX trial is incompatible. A locally computed hash only identifies a file; it does not make an unknown PyTorch checkpoint safe or suitable.
- Between 1 and 16 authorized representative still images, including intended resolutions, scene density and lighting. Labels are not required for this timing test. Accuracy still requires independently reviewed labels.
- Windows 64-bit Python 3.11, the working NVIDIA driver, internet/disk space for first-time installation, laptop power and ventilation.

Keep images under the ignored `capacity-data/` directory. Create `capacity-data/frames.json`:

```json
{"images": ["images/day-crowded.jpg", "images/dim-view.jpg"]}
```

Image paths are relative to the manifest directory and must remain inside it. From the repository root in Command Prompt:

```bat
benchmark-gpu-windows.cmd "C:\models\approved-ppe.pt" EXPECTED_64_CHARACTER_SHA256 "capacity-data\frames.json"
```

Replace the example path/hash with approved inputs. Paths may contain spaces when quoted. The launcher creates the ignored `.venv-capacity`, separate from webcam and GPU-smoke environments. It installs PyTorch 2.6.0+cu124 and torchvision 0.21.0+cu124 from the official PyTorch index, followed by the pinned benchmark requirements, then runs `pip check`. This is a local benchmark environment; it does not replace or certify the production worker image. Package installation uses the internet; the benchmark does not download model weights or upload images.

A bounded CUDA computation check runs first. The benchmark then verifies the checkpoint hash, loads the actual production detector and measures **1, 2, 4 and 8 camera equivalents**, each requesting **2 FPS**, for **120 seconds per level**, after warmup. Initial targets are per-camera p95 at most 500 ms, at least 95% of requested FPS and zero inference failures. These are explicit trial settings, not approved factory acceptance targets. Expect about eight minutes plus setup/warmup; the benchmark parent enforces its own overall process deadline. Installation time is not bounded by that deadline.

Reports are uniquely named `validation-results/gpu-check-*.json` and `capacity-results/gpu-inference-*.json`. Share the inference JSON for interpretation; no images are needed. It includes model/image hashes, GPU identity, per-camera achieved FPS/p95, missed slots/failures and per-level allocated/reserved VRAM peaks. Free/total VRAM is a point-in-time device reading **after** each level, not a sampled minimum; other applications affect it. Allocator peaks do not include other processes or all driver memory.

Interpretation:

- `inference_benchmark_completed` means the run completed, even if all levels failed. Read each printed PASS/FAIL and `inference_targets_met`.
- `highest_tested_passing_camera_equivalents` is the highest passing tested load, never a live-camera budget. When every tested level passes, the saturation limit has not been found.
- `highest_passing_tested_prefix` stops at the first failed tested level; it does not imply untested loads passed. `nonmonotonic_results=true` means a higher level passed after a lower one failed. Investigate competing workloads, thermal/power behavior and repeated trials before drawing conclusions.
- `deployment_camera_budget=null`, `camera_capacity_measured=false` and `production_approved=false` remain intentional. No decode, tracking/voting, storage, broker, alert delivery or camera freshness is measured here.

Preserve every report, not only the best run. Repeat under the intended laptop power/thermal settings. For longer/different sweeps, use `.venv-capacity\Scripts\python.exe` with the developer CLI in [PRODUCTION_CAPACITY.md](PRODUCTION_CAPACITY.md). Model load/OOM/runtime failures retain failed status without leaking native diagnostics; check model readiness separately when needed. Do not replace a failed CUDA run with CPU and report it as GPU capacity. After inference measurements, use an authorized live-camera pilot and sustained combined-load tests before setting scheduler budgets. No automatic 200-camera/factory or 1000-camera fleet estimate is produced.

The Python benchmark logic is regression-tested in cloud. The Windows batch launcher and actual laptop CUDA throughput must still be executed on Windows; cloud tests do not establish their hardware performance.
