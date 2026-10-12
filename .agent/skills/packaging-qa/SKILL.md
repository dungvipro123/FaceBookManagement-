---
name: packaging-qa
description: Integration testing, Playwright UI testing, performance benchmarking, PyInstaller packaging, and Windows autostart registry.
---

# Packaging & QA Skill

## Role & Boundaries
- **Owner Files**:
  - `app/autostart.py`
  - `tests/*`
  - `FBMetaHunter.spec`
  - `run_dev.bat`
  - `run_background.vbs`
  - `docs/TEST_REPORT.md`
- **Responsibilities**:
  - Windows registry helper for autostart (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
  - PyInstaller spec bundling assets and static files into windowed `FBMetaHunter.exe`.
  - Comprehensive pytest suite covering backend routes, secret masking, config hot-reload, dedupe, 429 retries.
  - Playwright visual testing verifying 4 tabs, canvas render, fallback, and mobile responsiveness.
  - Performance benchmarking: idle RAM, CPU, FPS.
