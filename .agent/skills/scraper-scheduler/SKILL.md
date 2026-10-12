---
name: scraper-scheduler
description: Playwright scraper worker loop, scheduled execution, Gemini deal analysis, anti-checkpoint delays, and failover.
---

# Scraper & Scheduler Skill

## Role & Boundaries
- **Owner Files**:
  - `app/scraper/engine.py`
  - `app/scraper/scheduler.py`
  - `app/scraper/appraiser.py`
  - `app/scraper/price_parser.py`
- **Responsibilities**:
  - Playwright browser execution in a dedicated worker thread or subprocess.
  - Round-robin queue for active monitored groups from SQLite.
  - Randomized delay patterns (scroll & group switch). Minimum interval 10 mins.
  - Automatic pause/backoff upon checkpoint or captcha detection.
  - Gemini price appraisal with multi-model failover (3.5-flash -> 3.1-flash-lite) and local regex fallback.
  - Deduplication check via database before AI processing.
