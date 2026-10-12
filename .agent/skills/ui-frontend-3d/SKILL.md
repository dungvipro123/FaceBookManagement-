---
name: ui-frontend-3d
description: Three.js 3D status core hero, particle field, dark command-center glassmorphism dashboard, 4-tab UI, i18n, and performance fallbacks.
---

# UI Frontend 3D Skill

## Role & Boundaries
- **Owner Files**:
  - `ui/index.html`
  - `ui/static/css/style.css`
  - `ui/static/js/app.js`
  - `ui/static/js/scene3d.js`
  - `ui/static/js/i18n.js`
  - `ui/static/vendor/three.module.js`
- **Responsibilities**:
  - Offline-first: Vendor Three.js locally in `ui/static/vendor/` via ES module importmap. No external CDN.
  - 3D Status Core: interactive orb/geometry with shader/particles reacting to real SSE events (slow green pulse, amber dimmed, red jitter, deal burst).
  - Background particle depth field with mouse/device parallax.
  - 4 glassmorphic tabs with 3D tilt effects: Overview, Groups, Discord Channels, System.
  - Performance optimization: pause render loop when `document.hidden`, auto performance mode fallback if FPS < 30.
  - Graceful 2D fallback when WebGL is unavailable or context lost.
  - Responsive at 375px (mobile LAN) and 1440px (desktop).
  - i18n support (Vietnamese default, English optional).
