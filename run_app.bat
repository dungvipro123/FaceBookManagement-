@echo off
title FB Monitor Hunter v2.0 - System Tray ^& 3D Dashboard
cd /d "%~dp0"

echo [FB Monitor Hunter v2.0] Khoi dong ung dung...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m app
) else (
    python -m app
)

pause
