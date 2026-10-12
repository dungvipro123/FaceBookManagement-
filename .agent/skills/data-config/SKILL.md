---
name: data-config
description: SQLite WAL database management, schema migrations, runtime configuration hot-reload, path resolution, and secret masking.
---

# Data & Config Skill

## Role & Boundaries
- **Owner Files**:
  - `app/db.py`
  - `app/config.py`
  - `app/models.py`
  - `app/paths.py`
- **Responsibilities**:
  - Resolve application directory in `%APPDATA%/FBMonitorHunter/`.
  - Resolve bundled static assets via `sys._MEIPASS` when packaged.
  - SQLite database initialized in WAL mode with connection-per-thread safety.
  - Idempotent schema migrations (`posts`, `monitored_groups`, `channel_configs`, `system_settings`).
  - Runtime configuration hot-reload without application restarts.
  - Secret masking helper: masks keys/tokens so only the last 4 characters are exposed.
