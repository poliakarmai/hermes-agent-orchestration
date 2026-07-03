# Data Models

This page documents the configuration structures, database schema, and data formats used across the Hermes orchestration system.

## 1. Tenant Configuration (tenant-config.yaml)

**File:** `/configs/tenant-config.yaml`

Example tenant profile configuration:

```yaml
model:
  base_url: https://api.deepseek.com/v1
  default: deepseek-v4-pro
  provider: custom

agent:
  max_turns: 100
  gateway_timeout: 1200
  disabled_toolsets:
    - delegation
    - code_execution

profile:
  role: user
  shared_skills: /opt/hermes/shared-skills
  instincts: /home/openclaw/.hermes/instincts
  sandbox: /home/hermes-ilya/
  tenant_name: ilya

platforms:
  telegram:
    home_channel: '470549555'

approvals:
  mode: always
```

### Fields

| Path | Type | Description |
|------|------|-------------|
| `model.base_url` | string | LLM API endpoint (DeepSeek v1) |
| `model.default` | string | Default model name |
| `model.provider` | string | Provider type |
| `agent.max_turns` | integer | Max conversation turns (100) |
| `agent.gateway_timeout` | integer | Gateway timeout in seconds (1200) |
| `agent.disabled_toolsets` | list | Toolsets blocked for this tenant |
| `profile.role` | string | Always `user` for tenants |
| `profile.shared_skills` | path | Shared skills mount point |
| `profile.instincts` | path | Instincts/safety rules |
| `profile.sandbox` | path | Linux sandbox home directory |
| `profile.tenant_name` | string | Short tenant identifier |
| `approvals.mode` | string | `always` (tenant) or `smart` (admin) |

### Tenant Profile Disk Layout

```
~/.hermes/profiles/user_<tg_id>/
├── config.yaml          # As above
├── .env                 # Environment (bot tokens, API keys)
├── .env.enc             # Age-encrypted copy of .env
├── skills/              # Auto-synced base skills
├── skills.local/        # Tenant modifications (never overwritten)
├── skills.imported/     # Archived imports
└── memory/              # Per-tenant memory files
```

## 2. Main Gateway Config (config.yaml)

**File:** `~/.hermes/config.yaml` (not in repo — live on production server)

Key sections relevant to orchestration:

```yaml
telegram:
  channel_profiles:
    '470549555': 'user_470549555'
    '696238708': 'user_696238708'
    # ... one entry per tenant Telegram user ID

  channel_prompts:
    '470549555': |
      Ты Hermes — AI-ассистент ilya.
      ...
    '696238708': |
      Ты Hermes — AI-ассистент ...
```

The `channel_profiles` dict maps Telegram user IDs to profile directory names. The `channel_prompts` dict contains per-tenant system prompts that define behavior and restrictions.

## 3. Skill Tiers (skill-tiers.yaml)

**File:** `/configs/skill-tiers.yaml`

Three-tier access control structure:

```yaml
admin_only:         # ~65 skills — admin (Poliakarm) only
  - bybit-trading
  - devops/cost-tracking
  - devops/hermes-multi-tenant
  - mlops/inference/*
  - devops/vpn-infra
  - engineering/*
  - autonomous-ai-agents/*
  - red-teaming/godmode
  - ... (full list in the file)

base:               # ~41 skills — auto-synced to ALL tenants
  - productivity/communication-protocol
  - productivity/hermes-constitution
  - meta/using-hermes-skills
  - note-taking/*
  - gws-shared
  - github/*
  - mcp/native-mcp
  - productivity/*
  - media/*
  - research/*
  - security/input-guardrails
  - software-development/plan
  - software-development/spike
  - software-development/requesting-code-review
  - software-development/subagent-driven-development
  - ... (full list in the file)

opt_in:             # ~26 skills — tenant requests → admin installs
  - creative/ascii-art
  - creative/comfyui
  - creative/image-generation-api
  - media/spotify
  - smart-home/openhue
  - health/moe-zdorovie
  - ... (full list in the file)
```

**Tier behavior:**
- `admin_only`: Synced only to default (admin) profile. Not copied to any tenant.
- `base`: Automatically synced to ALL tenants on every `skill-sync.py` run.
- `opt_in`: Tenant must request; admin installs via `skill-sync.py --install`.
- Skills promoted from `skills.local/` → `base` via review pipeline.

## 4. Payment Database Schema

**File:** `~/.hermes/data/stars_payments.db` (SQLite3)

### `payments` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK AUTO | Unique payment ID |
| `telegram_id` | INTEGER NOT NULL | Telegram user ID |
| `telegram_username` | TEXT | Telegram username (nullable) |
| `amount_stars` | INTEGER NOT NULL | Amount paid in Stars |
| `telegram_payment_id` | TEXT UNIQUE | Telegram payment charge ID |
| `status` | TEXT DEFAULT 'pending' | `pending` → `confirmed` → `activated` or `failed` |
| `expires_at` | TEXT | ISO datetime of subscription expiry |
| `created_at` | TEXT DEFAULT now | Local datetime |

### `pro_users` Table

| Column | Type | Description |
|--------|------|-------------|
| `telegram_id` | INTEGER PK | Telegram user ID |
| `telegram_username` | TEXT | Username |
| `activated_at` | TEXT | ISO datetime of activation |
| `expires_at` | TEXT NOT NULL | ISO datetime of expiry (30 days) |
| `active` | INTEGER DEFAULT 1 | 1=active, 0=expired |

### Payment Flow in DB

```
INSERT INTO payments (pending)
    → pre_checkout_query OK (Stars) / user clicks "I paid" (TON)
        → UPDATE payments SET status='confirmed'
            → stars-activator cron picks up
                → hermes-tenant onboard
                    → UPDATE payments SET status='activated'
                    → INSERT INTO pro_users
```

## 5. Skill Sync Directory Layout

```
~/.hermes/
├── skills/                     # BASE — source of truth
│   ├── productivity/
│   │   └── communication-protocol/
│   │       └── SKILL.md
│   ├── github/
│   │   └── github-auth/
│   │       └── SKILL.md
│   └── ... (one directory per skill)
│
├── config/
│   └── skill-tiers.yaml        # Tier definitions
│
└── profiles/
    └── user_<tg_id>/
        ├── skills/             # Auto-synced (base) — read-only for tenant
        ├── skills.local/       # Tenant modifications — never overwritten
        ├── skills.imported/    # Archive of skills promoted to base
        └── memory/             # Agent memory (per-tenant)
```

## 6. .env File Format

```
# Tenant .env — only TELEGRAM_BOT_TOKEN
# Encrypted via age. Private key: ~/.hermes/keys/hermes.key
TELEGRAM_BOT_TOKEN=123456:ABCdef...
```

Each tenant profile has its own `.env` with the system bot token. The file is encrypted with age after creation.

## 7. Data Flow Summary

```
┌─────────────────┐     ┌──────────────────────┐
│  skill-tiers    │────▶│  skill-sync.py       │
│  .yaml          │     │  (distribution       │
└─────────────────┘     │   engine)            │
                        │                      │
┌─────────────────┐     │  Reads: base tier    │
│  ~/.hermes/     │     │  Writes: tenant      │
│  skills/        │────▶│  profiles/skills/    │
└─────────────────┘     └──────────────────────┘

┌─────────────────┐     ┌──────────────────────┐
│  stars_payments │────▶│  stars-activator.py  │
│  .db            │     │  (cron, 2min)        │
│  (payments +    │     │                      │
│   pro_users)    │     │  Reads: confirmed    │
└─────────────────┘     │  payments            │
                        │  Calls: hermes-      │
┌─────────────────┐     │  tenant onboard      │
│  hermes-tenant  │◀────│                      │
│  CLI (onboard/  │     └──────────────────────┘
│   offboard/list)│
└─────────────────┘

┌─────────────────┐     ┌──────────────────────┐
│  tenant-config  │     │  ~/.hermes/config    │
│  .yaml          │────▶│  .yaml               │
│  (template)     │     │  (channel_profiles,  │
└─────────────────┘     │   channel_prompts)   │
                        └──────────────────────┘
```

## Source References

| Model | File | Purpose |
|-------|------|---------|
| Tenant profile | `/configs/tenant-config.yaml` | Template for new tenants |
| Skill tiers | `/configs/skill-tiers.yaml` | Access control definitions |
| Payment DB | `/scripts/stars-activator.py` (reads) + `/bots/miropolbot.py` (writes) | SQLite schema + access |
| Profile layout | `/scripts/hermes-tenant` | Profile creation logic |
| Main config format | `/scripts/hermes-tenant` | channel_profiles/prompts structure |
