# Architecture — Multi-Tenant Isolation & Bot Chain

## Overview

Hermes runs a **single Hermes Agent gateway** process serving multiple isolated users. Isolation is implemented at three layers — no separate gateway instances per tenant.

Sources: `/docs/01-infrastructure.md`, `/docs/orchestration-master.md`, `/docs/03-constitution.md`, `/README.md`

## Three-Layer Isolation Model

| Layer | Mechanism | What It Blocks |
|-------|-----------|----------------|
| **1. Toolsets** | `disabled_toolsets` from `channel_profiles` (in `config.yaml`) | Prevents tenants from spawning agents, running code, or using cron |
| **2. Channel Prompts** | `channel_prompts` with sandbox descriptions in `config.yaml` | LLM knows its own sandbox and not to reveal other tenants' boundaries |
| **3. Linux Users** | Separate Linux user (`hermes-<name>`), `chmod 770`, iptables | File system isolation, network isolation |

### What Tenants Cannot Do

- `delegation` — cannot delegate tasks to sub-agents
- `code_execution` — cannot execute arbitrary code
- `cronjob` — no personal cron
- `terminal` — no shell access

### What Tenants Get

- Full chat with DeepSeek V4 Pro via Hermes gateway
- ~44 base skills (communication, knowledge management, email, GitHub, Google Workspace)
- Per-tenant Obsidian vault for memory/knowledge storage
- iptables-isolated networking

## Bot Chain Architecture

```
User
  │
  ├─ @Apolaibot (demo, ~44 MB RAM)
  │   ├─ Lightweight Python script (apolaibot-demo.py)
  │   ├─ Direct DeepSeek API (no Hermes gateway)
  │   ├─ Rate limits: 30 RPM / 500 RPH (demo tier)
  │   ├─ Features: chat, /export pdf, /export docx, whisper, 2FA
  │   └─ /upgrade → @miropolbot
  │
  ├─ @miropolbot (Stars payment, ~10 MB RAM)
  │   ├─ Python polling script (miropolbot.py)
  │   ├─ /start → invoice (100 ⭐, 30 days Pro)
  │   ├─ successful_payment → hermes-tenant onboard
  │   └─ Alerts admin + notifies user
  │
  └─ @Morearbot (Pro, ~230 MB RAM)
      ├─ Full Hermes Agent gateway
      ├─ Multi-tenant with channel_profiles
      ├─ Per-tenant Obsidian vault
      └─ All Pro features unlocked
```

## Systemd Service Layout

All services run as **systemd user-level** units in `~/.config/systemd/user/`.

| Service | RAM | Type | Notes |
|---------|-----|------|-------|
| `apolaibot-demo.service` | ~44 MB | Python script (polling) | Demo bot, first point of contact |
| `miropolbot.service` | ~10 MB | Python script (long-polling) | Payment handler for Telegram Stars |
| `hermes-gateway.service` | ~230 MB | Hermes Agent | Multi-tenant Pro gateway |
| `hermes-gateway-demo.service` | (disabled) | Hermes Agent | **Disabled** — saves ~155 MB RAM |

## Deployment

- **Server:** Helsinki, Finland — 2.27.48.142 (Netshield LTD)
- **RAM:** 1.9 GB (NOT 64 GB!) + 2 GB swap — memory is the critical constraint
- **Gateway:** Hermes Agent (Nous Research), patched for profile-specific `disabled_toolsets`
- **LLM:** DeepSeek V4 Pro (`deepseek-v4-pro`)
- **Patch location:** `~/.hermes/hermes-agent/gateway/run.py` — profile-specific disabled_toolsets (may be lost on Hermes update)

## Profile Structure

Each tenant has a profile directory at `~/.hermes/profiles/<name>/` containing:

- `.env` — environment variables (age-encrypted)
- `config.yaml` — profile-specific Hermes config
- `skills/` — auto-synced base skills
- `skills.local/` — tenant modifications (never overwritten by sync)
- `skills.imported/` — archive of skills imported to base
- Obsidian vault (per-tenant, for memory/knowledge)

### Example Tenant Config (`configs/tenant-config.yaml`)

Key fields in a tenant config:
- `model.base_url` — DeepSeek API endpoint
- `agent.disabled_toolsets` — what tools the tenant can't use
- `agent.channel_prompt` — system prompt describing the tenant's sandbox
- `profile.sandbox` — Linux home directory for filesystem isolation
- `profile.tenant_name` — short identifier
- `approvals.mode` — `always`, `auto`, or `smart`

## Profiles in Production (as of June 2026)

- Default (admin) — full access: trading, delegation, code execution, cron
- user_470549555 (Ilya) — `disabled_toolsets: [delegation, code_execution]`
- 11 total tenants in production

## Source Map

| File/Directory | Purpose |
|----------------|---------|
| `docs/01-infrastructure.md` | Infrastructure details, bot chain, systemd services |
| `docs/03-constitution.md` | Constitution: user sovereignty, isolation, security rules |
| `docs/orchestration-master.md` | Full architecture document (Russian) |
| `configs/tenant-config.yaml` | Example tenant profile config |
| `configs/skill-tiers.yaml` | Skill access tiers per profile type |
