---
name: discord-delivery
description: Multi-channel Discord delivery via Webhooks, discount filtering, mention modes, image toggles, rate-limit retry, and optional bot gateway.
---

# Discord Delivery Skill

## Role & Boundaries
- **Owner Files**:
  - `app/discord/notifier.py`
  - `app/discord/bot_client.py`
  - `app/discord/formatting.py`
- **Responsibilities**:
  - Webhook delivery to 4 distinct channels (`deal_1`, `deal_2`, `buy`, `log`).
  - Per-channel filtering: enable switch, min-discount %, mention mode (`@everyone`, `@here`, none), thumbnail toggle.
  - Honors HTTP 429 `Retry-After` header with backoff.
  - Optional Discord bot connection for 2-way slash command handling.
