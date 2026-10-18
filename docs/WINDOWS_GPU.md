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
