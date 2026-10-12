---
name: tray-app
description: Windows system tray integration via pystray, dynamic icon states, context menus, and browser/webview launch.
---

# Tray App Skill

## Role & Boundaries
- **Owner Files**:
  - `app/tray.py`
  - `app/assets/icon.ico`
  - `app/assets/icon.png`
- **Responsibilities**:
  - Main thread integration with `pystray`.
  - Icon state colors reflecting AppState within 2 seconds (green = normal, yellow = paused/scanning, red = error).
  - Context menu: Open Dashboard, Scan Now, Pause/Resume, Start with Windows, Quit.
  - Left click opens dashboard in default browser (or pywebview window if available).
  - Graceful teardown signaling the supervisor stop event.
