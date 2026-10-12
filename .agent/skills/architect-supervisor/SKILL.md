---
name: architect-supervisor
description: Manages application lifecycle, shared AppState, thread orchestration, single-instance mutex, and logging setup.
---

# Architect Supervisor Skill

## Role & Boundaries
- **Owner Files**:
  - `app/__init__.py`
  - `app/__main__.py`
  - `app/supervisor.py`
  - `app/state.py`
  - `app/logging_setup.py`
  - `docs/PLAN.md`
  - `docs/CONTRACTS.md`
- **Responsibilities**:
  - Single-instance Windows mutex to prevent multiple instances.
  - Global unhandled exception hook logging to `%APPDATA%/FBMonitorHunter/logs/`.
  - Main thread lifecycle: owns the `pystray` event loop on main thread.
  - Spawns background worker thread for FastAPI/Discord event loop.
  - Spawns dedicated background worker thread for the Playwright scraper loop.
  - Thread-safe `AppState` management and graceful shutdown via `threading.Event`.
