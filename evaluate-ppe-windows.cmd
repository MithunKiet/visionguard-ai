@echo off
setlocal EnableExtensions
title VisionGuard - Local PPE accuracy evaluation
if "%~1"=="" goto usage
rem Resolve the caller's manifest path before changing directories.
set "VG_PPE_MANIFEST=%~f1"
if not exist "%VG_PPE_MANIFEST%" goto usage
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv-webcam\Scripts\python.exe" goto missing_setup
set "VG_PPE_REPORT="
for /f %%G in ('.venv-webcam\Scripts\python.exe -c "import uuid; print(uuid.uuid4().hex)"') do set "VG_PPE_REPORT=ppe-accuracy-%%G.json"
if not defined VG_PPE_REPORT goto failed
cd ai-worker
"..\.venv-webcam\Scripts\python.exe" -m src.validation.ppe_evaluate --manifest "%VG_PPE_MANIFEST%" --output "..\validation-results\%VG_PPE_REPORT%"
if errorlevel 1 goto failed
echo.
echo Report: validation-results\%VG_PPE_REPORT%
echo These are frame metrics against your labels, not production approval.
popd
pause
exit /b 0

:missing_setup
echo Run test-ppe-windows.cmd first to install the inference dependencies and verified model.
goto failed
:failed
echo Evaluation did not complete. Check the error above and docs\PPE_ACCURACY_EVALUATION.md.
popd
pause
exit /b 1
:usage
echo Provide the path to your labeled dataset manifest, for example:
echo evaluate-ppe-windows.cmd "validation-data\webcam-held-out\manifest.json"
echo See docs\PPE_ACCURACY_EVALUATION.md for label preparation.
pause
exit /b 2
