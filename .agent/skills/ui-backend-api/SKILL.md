---
name: ui-backend-api
description: FastAPI backend server, REST endpoints for settings/groups/channels, PIN authentication for LAN, and SSE log streaming.
---

# UI Backend API Skill

## Role & Boundaries
- **Owner Files**:
  - `app/api/__init__.py`
  - `app/api/server.py`
  - `app/api/routes_status.py`
  - `app/api/routes_groups.py`
  - `app/api/routes_channels.py`
  - `app/api/routes_settings.py`
  - `app/api/routes_logs.py`
- **Responsibilities**:
  - FastAPI web server listening on 127.0.0.1 by default (or 0.0.0.0 if LAN mode enabled).
  - PIN header verification when accessing from non-loopback IP addresses.
  - Server-Sent Events (`/api/logs/stream`) for realtime logging and status triggers.
  - CRUD REST endpoints for Groups, Discord Channels, and System Settings.
  - Immediate trigger endpoints: `/api/actions/scan-now`, `/api/actions/pause`, `/api/actions/resume`, `/api/actions/test-quota`.
  - Mask all secrets in all JSON responses.
