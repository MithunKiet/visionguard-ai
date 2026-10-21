@echo off
setlocal EnableExtensions DisableDelayedExpansion
title VisionGuard - Local GPU inference capacity
if "%~3"=="" goto usage
rem Resolve paths relative to the caller before changing directories.
set "VG_CAP_WEIGHTS=%~f1"
set "VG_CAP_HASH=%~2"
set "VG_CAP_MANIFEST=%~f3"
if not exist "%VG_CAP_WEIGHTS%" goto usage
if not exist "%VG_CAP_MANIFEST%" goto usage
pushd "%~dp0"
if errorlevel 1 exit /b 1
echo Local inference-only benchmark. No camera connections, uploads or alerts.
echo Use a trusted production nine-class PPE checkpoint and its independently reviewed SHA-256.
echo The six-class webcam ONNX model is incompatible with this benchmark.
echo Connect laptop power and close competing GPU applications.
echo First run downloads a separate CUDA inference environment; installation may take several minutes.
py -3.11 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto failed
if not exist ".venv-capacity\Scripts\python.exe" (
    py -3.11 -m venv .venv-capacity
    if errorlevel 1 goto failed
)
".venv-capacity\Scripts\python.exe" -m pip install --disable-pip-version-check --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0+cu124 torchvision==0.21.0+cu124
if errorlevel 1 goto failed
".venv-capacity\Scripts\python.exe" -m pip install --disable-pip-version-check -r ai-worker\gpu-capacity-requirements.txt
if errorlevel 1 goto failed
".venv-capacity\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
set "VG_CAP_ID="
for /f %%G in ('.venv-capacity\Scripts\python.exe -c "import uuid; print(uuid.uuid4().hex)"') do set "VG_CAP_ID=%%G"
if not defined VG_CAP_ID goto failed
cd ai-worker
"..\.venv-capacity\Scripts\python.exe" -m src.validation.gpu_check --output "..\validation-results\gpu-check-%VG_CAP_ID%.json"
if errorlevel 1 goto failed
"..\.venv-capacity\Scripts\python.exe" -m src.capacity.benchmark --weights "%VG_CAP_WEIGHTS%" --model-sha256 "%VG_CAP_HASH%" --manifest "%VG_CAP_MANIFEST%" --device cuda --cameras 1 2 4 8 --fps 2 --seconds 120 --p95-ms 500 --min-fps-ratio 0.95 --output "..\capacity-results\gpu-inference-%VG_CAP_ID%.json"
if errorlevel 1 goto failed
echo Report: capacity-results\gpu-inference-%VG_CAP_ID%.json
echo Completed does not mean every load passed. Read per-level PASS/FAIL results.
echo Live camera decoding, accuracy and production capacity remain unmeasured.
popd
pause
exit /b 0
:failed
echo Benchmark did not complete. Check Python 3.11, CUDA, trusted model/hash, manifest and installation errors.
echo Preserve any reports. Do not disable TLS checks or switch silently to CPU.
popd
pause
exit /b 1
:usage
echo Usage: benchmark-gpu-windows.cmd "C:\models\ppe.pt" EXPECTED_SHA256 "C:\capacity-data\frames.json"
echo Requires a trusted nine-class production PPE checkpoint and 1-16 representative still images.
echo See docs\WINDOWS_GPU.md. No labels are needed for timing; this does not measure accuracy.
pause
exit /b 2
