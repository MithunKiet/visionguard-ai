# Check your Windows laptop webcam

This first step checks that your webcam opens and produces video. It displays a local preview for 30 seconds and saves a small JSON report with resolution and frame-rate measurements. It does **not** record footage, access your microphone, upload frames, detect PPE or send alerts. The cloud workspace cannot access your laptop webcam.

## Start

1. Install **Python 3.11 for Windows** from https://www.python.org/downloads/windows/ and include the Python launcher. No GPU, Docker, RTSP server or camera password is needed.
2. Download the `feat/real-camera-validation` branch of this repository as a ZIP and extract it. If you use Git, check out that branch and pull its latest changes first.
3. Close Camera, Teams, Zoom and other applications using the webcam. Open any physical camera privacy shutter. In Windows Settings, find Camera privacy and enable camera access for desktop apps (Windows 11: Privacy & security → Camera; Windows 10: Privacy → Camera).
4. Double-click **`check-webcam-windows.cmd`** in the extracted project folder. The first run creates a separate `.venv-webcam` environment and installs NumPy/OpenCV from the pinned requirements; internet is needed for dependency installation. No administrator access or execution-policy change is required.
5. Allow the preview to run for 30 seconds. Press Q, Esc or close its window to stop early; an early stop is reported as cancelled, not as a completed check. The command window stays open so you can read any error.

The launcher prints a report filename under `validation-results/`. Share that **JSON report**, or its status, dimensions and frame-rate values. Do not send passwords. The report contains no photos, video or camera connection credentials.

## If the camera does not open

Check Windows camera permissions, the physical shutter, and other camera applications first. If necessary, open Command Prompt in the extracted project folder and try Windows Media Foundation:

```bat
check-webcam-windows.cmd 0 msmf
```

For a second/USB webcam, try:

```bat
check-webcam-windows.cmd 1
```

The default is camera index 0 using DirectShow. The process has a deadline in case a camera driver hangs. A virtual camera may occupy index 0; use the preview to confirm you selected the physical webcam. Windows N editions may need the Microsoft Media Feature Pack; managed company laptops may require IT to enable camera access. Do not disable security controls to work around an installation error.

## What comes next

Once capture works, supply a trusted PPE checkpoint compatible with this project's detector and independently labeled test examples. There are currently no compatible weights installed in the cloud workspace. A generic person detector cannot establish whether a helmet or vest is present. Follow [REAL_CAMERA_VALIDATION.md](REAL_CAMERA_VALIDATION.md) for model and label requirements.

A laptop webcam is useful for an initial close-range check. Its results cannot establish performance for factory cameras at different heights, distances, angles or lighting conditions. No minimum webcam result is treated as production approval.

For developers, the equivalent CLI (from `ai-worker/`) is:

```bat
..\.venv-webcam\Scripts\python.exe -m src.validation.camera webcam --camera-index 0 --seconds 30 --output ..\validation-results\webcam-manual.json
```

Add `--no-preview` for measurement only. Choose a new report path on every run; evidence files are never overwritten. Keep GUI OpenCV in the dedicated webcam environment rather than installing it alongside the worker's `opencv-python-headless` package.
