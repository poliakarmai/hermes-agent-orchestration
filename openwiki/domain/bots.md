# Bots

This page documents the three Telegram bots that form the user-facing layer of the Hermes platform. They form a chain: demo → payment → full Pro access.

## Bot Chain Overview

```
@Apolaibot (free demo)
    → /upgrade → @Miropolbot (payment)
        → Payment confirmed → stars-activator (cron)
            → hermes-tenant onboard
                → @Morearbot (full Hermes Pro)
```

## 1. @Apolaibot — Demo Bot

**File:** `/bots/apolaibot-demo.py` (193 lines)

**Purpose:** Lightweight demo bot for trial users. Provides basic AI chat to showcase capabilities. When users need more, it directs them to `/upgrade`.

**Architecture decision:** This is intentionally NOT a Hermes gateway instance. It's a standalone Python script using `python-telegram-bot` library that calls an OpenAI-compatible API directly (DeepSeek by default). This saves ~155MB RAM compared to running a full Hermes gateway for demo users.

**Key features:**
- Chat with OpenAI-compatible API (DeepSeek, configurable via `.env`)
- `/start` — welcome message
- `/upgrade` — directs to @Miropolbot for payment
- Prompt injection sanitization (R3 fix: 8 regex patterns)
- Conversation persistence to disk (R4 fix: JSON file, 7-day TTL)
- SSL verification enabled (R8 fix)
- Systemd-managed: `~/.config/systemd/user/apolaibot-demo.service`

**Configuration (loaded from `~/.hermes/profiles/demo/.env`):**
| Env Var | Default | Purpose |
|---------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | (required) | Telegram bot token |
| `APOLAIBOT_API_URL` | `https://api.deepseek.com/v1` | LLM API endpoint |
| `DEEPSEEK_API_KEY` / `APOLAIBOT_API_KEY` | (required) | API authentication |
| `APOLAIBOT_MODEL` | `deepseek-chat` | Model name |
| `APOLAIBOT_STATE_DIR` | `~/.local/share/apolaibot` | State persistence directory |

**Security:**
- 8 prompt injection patterns checked before sending to LLM (R3)
- Input truncated to 8000 chars
- Blocked messages return `[blocked: prompt injection detected]`
- Conversations expire after 7 days of inactivity
- State saved atomically via `os.replace()`

## 2. @Miropolbot — Payment Handler

**File:** `/bots/miropolbot.py` (242 lines)

**Purpose:** Handles payment collection for Pro subscriptions. Supports two payment methods:
- **Telegram Stars** (XTR, in-chat) — 1060 ⭐ (~1800₽)
- **TON via CryptoBot** (~14 TON, ~1800₽)

**Architecture:** Long-polling bot (not webhook). Uses raw `urllib` requests to Telegram API — no external dependencies beyond the standard library and SQLite3.

**How it works:**

```
User sends /start
    → Bot shows inline keyboard: Stars or TON

Stars path:
    → sendInvoice → user pays in-chat
    → pre_checkout_query → auto-approve if amount >= 1060
    → successful_payment → save to SQLite payments table

TON path:
    → createInvoice via CryptoBot API
    → user receives external payment link
    → user pays in @CryptoBot
    → user clicks "I paid" → check_ton → verify via CryptoBot API
    → activate_ton_pro → save to SQLite pro_users table
```

**Payment DB (`~/.hermes/data/stars_payments.db`):**

Two tables:
- **`payments`** — tracks individual payment transactions
- **`pro_users`** — tracks active subscriptions (telegram_id, activated_at, expires_at, active)

**Key details:**
- Pro price: 1060 Stars or 14 TON (~1800₽ as of June 2026)
- Subscription duration: 30 days
- Stars payment is instant (Telegram handles the transaction)
- TON requires external CryptoBot flow with manual "I paid" check
- TON support added in commit `3fdb6fa` (latest commit at documentation time)

## 3. @Morearbot — Full Hermes Gateway

**File:** Not in this repository (part of the main Hermes agent codebase)

**Purpose:** Production Hermes gateway serving all paying tenants. Single process routes users to their profiles via `channel_profiles`.

**Key properties:**
- ~200MB RAM
- Full toolset (for admin), restricted tools (for tenants)
- Profile-specific `disabled_toolsets` via patched `gateway/run.py`
- Routes by Telegram user ID → `channel_profiles` in `~/.hermes/config.yaml`
- Per-tenant system prompts via `channel_prompts`

**Important note for agents:** The gateway source code is NOT in this repository. This repo only contains the orchestration configs and scripts that manage gateway behavior. The gateway lives in the upstream `hermes-agent` project.

## Bot Lifecycle Summary

| Stage | Bot | RAM | Type | User Sees |
|-------|-----|-----|------|-----------|
| 1. Trial | @Apolaibot | ~45MB | Python script | Free chat + /upgrade |
| 2. Payment | @Miropolbot | ~10MB | Python script | Payment UI (Stars/TON) |
| 3. Pro | @Morearbot | ~200MB | Hermes Gateway | Full AI + tools + memory |

## Source References

| Bot | File | Lines | Dependencies |
|-----|------|-------|-------------|
| @Apolaibot | `/bots/apolaibot-demo.py` | 193 | python-telegram-bot, aiohttp |
| @Miropolbot | `/bots/miropolbot.py` | 242 | stdlib only (urllib, sqlite3) |
| Activator | `/scripts/stars-activator.py` | 75 | subprocess, sqlite3 |

## Change Guidance

When modifying these bots:

1. **@Apolaibot changes:** Test conversation persistence (load/save from disk), sanitization patterns, and API error handling. The prompt injection regex patterns are the most sensitive area.
2. **@Miropolbot changes:** The TON flow involves external CryptoBot API calls — test with real invoices. The pre_checkout_query auto-approve logic must verify amount >= PRICE.
3. **stars-activator changes:** This runs as cron — it must be idempotent. The `onboard_tenant` call must handle failures gracefully (DB rollback or retry).
4. **All bots:** Bot tokens are in encrypted `.env` files. Never log or expose tokens.
