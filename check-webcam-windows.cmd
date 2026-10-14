@echo off
setlocal EnableExtensions
title VisionGuard - Windows webcam check
pushd "%~dp0"
if errorlevel 1 exit /b 1

echo VisionGuard webcam check - no recording or upload.
echo Close Camera, Teams, Zoom and other apps using your webcam first.
echo This checks the camera only. PPE detection needs a trained model.
echo.
py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" >nul 2>&1
if errorlevel 1 goto missing_python

if not exist ".venv-webcam\Scripts\python.exe" (
    py -3.11 -m venv .venv-webcam
    if errorlevel 1 goto setup_failed
)
".venv-webcam\Scripts\python.exe" -m pip install --disable-pip-version-check -r "ai-worker\webcam-requirements.txt"
if errorlevel 1 goto setup_failed

set "VG_WEBCAM_INDEX=0"
if not "%~1"=="" set "VG_WEBCAM_INDEX=%~1"
set "VG_WEBCAM_BACKEND=directshow"
if not "%~2"=="" set "VG_WEBCAM_BACKEND=%~2"
set "VG_WEBCAM_REPORT="
for /f %%G in ('py -3.11 -c "import uuid; print(uuid.uuid4().hex)"') do set "VG_WEBCAM_REPORT=webcam-%%G.json"
if not defined VG_WEBCAM_REPORT goto setup_failed
cd ai-worker
"..\.venv-webcam\Scripts\python.exe" -m src.validation.camera webcam --camera-index "%VG_WEBCAM_INDEX%" --backend "%VG_WEBCAM_BACKEND%" --seconds 30 --output "..\validation-results\%VG_WEBCAM_REPORT%"
if errorlevel 1 goto camera_failed
echo.
echo Camera check completed. Report: validation-results\%VG_WEBCAM_REPORT%
echo This is a camera check, not a PPE accuracy result.
popd
pause
exit /b 0

:missing_python
echo Install Python 3.11 for Windows from https://www.python.org/downloads/windows/
echo Include the Python launcher, then run this file again.
goto failed

:setup_failed
echo Setup failed. Check the error above and your internet connection.
goto failed

:camera_failed
echo The camera check did not complete. Q or closing the preview also stops it early.
echo Check Windows Settings - Camera privacy - Allow desktop apps to access your camera.
echo Close other camera apps and check the webcam privacy shutter.
echo From Command Prompt, try: check-webcam-windows.cmd 0 msmf
echo For another webcam, try: check-webcam-windows.cmd 1

:failed
popd
pause
exit /b 1
