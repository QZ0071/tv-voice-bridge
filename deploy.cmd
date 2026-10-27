@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 deploy.py --apply --download-adb %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10+ is required. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  python deploy.py --apply --download-adb %*
)
if errorlevel 1 echo Deployment did not complete. Read the diagnostic output above.
pause
