@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Install.cmd first.
  pause
  exit /b 1
)
if "%~1"=="" (
  ".venv\Scripts\python.exe" wireless_probe.py probe
) else (
  ".venv\Scripts\python.exe" wireless_probe.py %*
)
pause
