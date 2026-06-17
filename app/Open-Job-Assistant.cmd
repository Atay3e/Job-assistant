@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Job-Assistant.ps1" -Open
if errorlevel 1 (
  echo.
  echo Job Assistant failed to start. Please screenshot this window for debugging.
  pause
)
