@echo off
setlocal EnableExtensions
title VisionGuard - Local CUDA check
pushd "%~dp0"
if errorlevel 1 exit /b 1
echo Local GPU check: no camera, recording, model download or alerts.
echo The first run downloads the pinned CUDA PyTorch runtime into .venv-gpu.
echo Connect laptop power and close heavy GPU applications before continuing.
echo.
py -3.11 -c "import struct,sys; assert sys.version_info[:2] == (3, 11) and struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto missing_python
if not exist ".venv-gpu\Scripts\python.exe" (
    py -3.11 -m venv .venv-gpu
    if errorlevel 1 goto setup_failed
)
".venv-gpu\Scripts\python.exe" -m pip install --disable-pip-version-check --index-url https://download.pytorch.org/whl/cu124 -r "ai-worker\gpu-check-requirements.txt"
if errorlevel 1 goto setup_failed
set "VG_GPU_REPORT="
for /f %%G in ('py -3.11 -c "import uuid; print(uuid.uuid4().hex)"') do set "VG_GPU_REPORT=gpu-check-%%G.json"
if not defined VG_GPU_REPORT goto setup_failed
cd ai-worker
"..\.venv-gpu\Scripts\python.exe" -m src.validation.gpu_check --output "..\validation-results\%VG_GPU_REPORT%"
if errorlevel 1 goto check_failed
echo.
echo CUDA computation verified. Report: validation-results\%VG_GPU_REPORT%
echo This is not a PPE accuracy result or a camera capacity measurement.
popd
pause
exit /b 0

:missing_python
echo Install 64-bit Python 3.11 with the Python launcher, then retry.
goto failed
:setup_failed
echo GPU runtime setup failed. Check the error above and access to download.pytorch.org.
echo Do not disable certificate checks. See docs\WINDOWS_GPU.md.
goto failed
:check_failed
echo GPU check failed. Report, if written: validation-results\%VG_GPU_REPORT%
echo Share the JSON report. See docs\WINDOWS_GPU.md for troubleshooting.
:failed
popd
pause
exit /b 1
