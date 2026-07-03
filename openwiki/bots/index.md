# Bots — Telegram Bot Implementations

Three bots form the user acquisition and delivery pipeline. Two are defined in this repository; the third (@Morearbot) is the Hermes gateway itself, configured here.

## Bot Chain Overview

```
User → @Apolaibot (demo, 44MB) → /upgrade
                                    → @miropolbot (Stars, 10MB)
                                    → @Morearbot (Pro, 230MB)
```

## 1. @Apolaibot — Demo Bot

**File:** `/bots/apolaibot-demo.py`

The demo bot is the first point of contact. It is intentionally kept lightweight (~86 lines of core logic, ~44 MB RAM) by calling DeepSeek API directly instead of running a full Hermes gateway.

### Features

- **AI Chat:** Direct DeepSeek V4 Pro API with streaming
- **Rate Limiting:** 30 RPM / 500 RPH (demo tier) — uses `rate_limiter.py`
- **Audit Trail:** All conversations logged via `tenant-audit.py` integration
- **/upgrade:** Prompts user to upgrade to Pro (sends link/info to @miropolbot)
- **/export pdf & /export docx:** Document export from conversation
- **Whisper Integration:** Voice message transcription (lazy-loads `whisper` model)
- **2FA (TOTP):** Admin-only two-factor authentication via `pyotp`
- **Agent FS:** Versioned file operations for file management

### Security Features (added in commit 8bc4269)

- TOTP-based 2FA for admin operations
- Temporary rate limiting against abuse
- Input guards against injection
- IP-based tracking

### Key Implementation Details

```python
# Core pattern: imports from hermes_config.py for admin IDs
from hermes_config import ADMIN_IDS

# Optional dependencies with graceful fallback
try:
    import pyotp
    TOTP_ENABLED = True
except ImportError:
    TOTP_ENABLED = False

try:
    import whisper
    WHISPER_ENABLED = True
except ImportError:
    WHISPER_ENABLED = False
```

### Running

```bash
export TELEGRAM_BOT_TOKEN=<token>
python3 bots/apolaibot-demo.py
```

## 2. @miropolbot — Stars Payment Handler

**File:** `/bots/miropolbot.py`

A minimalist Telegram Stars payment handler using long-polling (not webhooks). It processes the entire payment lifecycle.

### Features

- **/start → Invoice:** Creates Telegram Stars invoice for 100 ⭐ (30 days Pro)
- **pre_checkout_query handling:** Validates payment amount, answers OK
- **successful_payment processing:** Saves to SQLite DB, notifies user and admin
- **SQLite Database:** `~/.hermes/data/stars_payments.db` with `payments` and `pro_users` tables
- **Long-polling loop:** `getUpdates` with 10-second timeout, no webhook

### Payment Flow

1. User sends `/start` → bot calls `sendInvoice` with XTR currency, `pro_monthly_30days` payload
2. Telegram sends `pre_checkout_query` → bot validates amount (≥ 100 ⭐) → answers OK
3. User confirms payment → Telegram sends `successful_payment`
4. Bot calls `save_payment()` → inserts into `payments` and `pro_users` tables
5. Bot sends confirmation: "Write /start in @Morearbot 🚀"
6. Background: `stars-activator.py` (cron 2 min) detects the pending activation and runs `hermes-tenant onboard`

### Running

```bash
export STARS_BOT_TOKEN=<token>
python3 bots/miropolbot.py
```

## 3. @Morearbot — Pro Gateway

**Not defined in this repo** — it is the main Hermes Agent gateway process, configured through:
- `~/.hermes/config.yaml` — `channel_profiles`, `channel_prompts`, `disabled_toolsets`
- `~/.hermes/profiles/<name>/` — per-tenant configs
- `configs/skill-tiers.yaml` — skill access control

This repository contains the orchestration layer that manages @Morearbot: onboarding/offboarding tenants, syncing skills, monitoring, and billing.

## Security & Operational Notes

- **Bot tokens:** Set via environment variables (`TELEGRAM_BOT_TOKEN`, `STARS_BOT_TOKEN`)
- **Permissions:** Bots run as systemd services under user-level systemd
- **Error handling:** Polling bots have `ERROR_SLEEP=5` seconds on failure
- **No webhooks:** @miropolbot uses long-polling; no webhook endpoint needed

## Source Map

| File | Bot | Lines (approx) |
|------|-----|-----------------|
| `bots/apolaibot-demo.py` | @Apolaibot | ~900 |
| `bots/miropolbot.py` | @miropolbot | ~86 |
