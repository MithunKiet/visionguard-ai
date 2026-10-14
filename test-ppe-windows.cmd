@echo off
setlocal EnableExtensions
title VisionGuard - Local PPE webcam trial
pushd "%~dp0"
if errorlevel 1 exit /b 1
echo Local PPE trial: camera frames stay on your laptop. No recording or alerts.
echo This public model can miss helmets, vests and violations. It is not production validated.
echo Close Camera, Teams and Zoom before continuing.
echo Model source and license: docs\PPE_WEBCAM_TRIAL.md
echo.
py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" >nul 2>&1
if errorlevel 1 goto missing_python
if not exist ".venv-webcam\Scripts\python.exe" (
    py -3.11 -m venv .venv-webcam
    if errorlevel 1 goto setup_failed
)
".venv-webcam\Scripts\python.exe" -m pip install --disable-pip-version-check -r "ai-worker\ppe-trial-requirements.txt"
if errorlevel 1 goto setup_failed
set "VG_PPE_CAMERA=0"
if not "%~1"=="" set "VG_PPE_CAMERA=%~1"
set "VG_PPE_BACKEND=directshow"
if not "%~2"=="" set "VG_PPE_BACKEND=%~2"
set "VG_PPE_REPORT="
for /f %%G in ('py -3.11 -c "import uuid; print(uuid.uuid4().hex)"') do set "VG_PPE_REPORT=ppe-trial-%%G.json"
if not defined VG_PPE_REPORT goto setup_failed
cd ai-worker
"..\.venv-webcam\Scripts\python.exe" -m src.validation.ppe_trial --download
if errorlevel 1 goto model_failed
echo.
echo Starting a 60-second preview. Press Q or Esc to finish earlier.
echo Test in a safe indoor area with good lighting and your head and torso visible.
"..\.venv-webcam\Scripts\python.exe" -m src.validation.ppe_trial --camera-index "%VG_PPE_CAMERA%" --backend "%VG_PPE_BACKEND%" --seconds 60 --output "..\validation-results\%VG_PPE_REPORT%"
if errorlevel 1 goto trial_failed
echo.
echo Trial finished. Report: validation-results\%VG_PPE_REPORT%
echo Counts are repeated boxes across frames, not unique people or measured accuracy.
popd
pause
exit /b 0

:missing_python
echo Install Python 3.11 with the Python launcher, then retry.
goto failed
:setup_failed
echo Dependency setup failed. Check the error above and your internet connection.
goto failed
:model_failed
echo Model download or checksum verification failed. Do not bypass verification.
echo Check access to raw.githubusercontent.com. If the cached model is corrupt,
echo remove only ai-worker\models\safety_gear_trial.onnx and retry.
goto failed
:trial_failed
echo Trial did not complete. Close other camera apps and check camera privacy permissions.
echo Try: test-ppe-windows.cmd 0 msmf
echo For another webcam: test-ppe-windows.cmd 1
:failed
popd
pause
exit /b 1
