@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 wallpaper_deploy.py --apply --download-adb %*
) else (
  python wallpaper_deploy.py --apply --download-adb %*
)
pause
