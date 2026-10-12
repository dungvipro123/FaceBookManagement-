# FB Monitor Hunter v2.0 - System Architecture & UI Plan

## 1. System Architecture
- **Process Model**:
  - Main Thread: Windows System Tray (`pystray`) event loop.
  - Worker Thread 1: Asyncio loop running FastAPI web server & optional Discord gateway bot.
  - Worker Thread 2: Dedicated worker running Playwright Scraper loop with scheduled execution.
  - Shared synchronization: Single `AppState` dataclass with thread-safe lock & `threading.Event` stop signal.
- **Single Instance & Mutex**:
  - Windows named mutex `Global\FBMonitorHunter_SingleInstanceMutex`.
  - Exits gracefully if an instance is already running.
- **Data & Paths**:
  - Application data root: `%APPDATA%/FBMonitorHunter/`.
  - Subdirectories: `logs/` (rotating logs `app.log`), `data/` (`facebook_posts.db`, `config.json`).
  - Bundled asset resolver: `sys._MEIPASS` for packaged exe fallback to local directory.
- **Database & Secrets**:
  - SQLite in WAL (`PRAGMA journal_mode=WAL`) mode, one connection per thread.
  - Secrets loaded from `%APPDATA%/FBMonitorHunter/.env` or local `.env`.
  - Runtime configuration stored in SQLite with hot-reload listeners.

## 2. 4-Tab Web Dashboard Specification
- **Theme**: Dark command-center aesthetic, monospace numeric display, high contrast, subtle glassmorphic panels.
- **Visuals**:
  1. Status Core Hero: 3D interactive orb (Three.js local vendor) reacting to SSE status events (green pulse, amber slow, red jitter, deal burst).
  2. Depth particle field with mouse/device parallax.
  3. Responsive across mobile (375px) and desktop (1440px).
- **Tabs**:
  - **Tab 1: Overview**: Realtime counters (Total Posts, Hot Deals, Buyers), Gemini quota latency sparkline, Scan Now trigger button, SSE Live Log terminal.
  - **Tab 2: Groups**: Monitored Facebook groups table with toggle switch, Add Group form, Delete with confirmation toast.
  - **Tab 3: Discord Channels**: 4 channels (`deal_1`, `deal_2`, `buy`, `log`) with masked webhook URL, toggle switch, discount threshold slider, mention selector (`@everyone`, `@here`, none), image toggle, and test message button.
  - **Tab 4: System**: Masked API keys (Gemini Key, Discord Token), scan interval slider, Headless mode toggle, Windows autostart toggle, LAN access toggle + PIN protection.
