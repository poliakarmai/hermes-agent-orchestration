# Architecture Overview

## Hermes Multi-Tenant Orchestration

This document describes the runtime architecture of the Hermes multi-tenant AI agent platform as configured and operated from this repository.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Production Server                      │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  @Apolaibot   │    │ @Miropolbot  │                   │
│  │  (demo bot)   │    │ (payments)   │                   │
│  │  ~45MB RAM    │    │ ~10MB RAM    │                   │
│  │  python-tele- │    │ long-polling │                   │
│  │  gram-bot     │    │              │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                            │
│         │  /upgrade         │ successful_payment         │
│         ▼                   ▼                            │
│  ┌──────────────────────────────────────┐               │
│  │         @Morearbot                   │               │
│  │    Hermes Gateway (single process)   │               │
│  │         ~200MB RAM                   │               │
│  │                                      │               │
│  │  channel_profiles → route by tg_id   │               │
│  │  channel_prompts  → per-tenant       │               │
│  │                   system prompt      │               │
│  └──────────────────────┬───────────────┘               │
│                         │                                │
│          ┌──────────────┼──────────────┐                │
│          ▼              ▼              ▼                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐          │
│  │ Profile    │ │ Profile    │ │ Profile    │  ...      │
│  │ default    │ │ user_470.. │ │ user_696.. │          │
│  │ (admin)    │ │ (tenant)   │ │ (tenant)   │          │
│  └────────────┘ └────────────┘ └────────────┘          │
└─────────────────────────────────────────────────────────┘
```

**Key decision (16.06.2026):** Demo bot uses Option B — a lightweight Python script using OpenAI-compatible API directly, without the full Hermes gateway. This saves ~155MB RAM per demo instance. Production tenants use the full Hermes gateway.

## Three-Layer Isolation

This is the foundational security architecture — never break this chain.

| Layer | Mechanism | What It Protects |
|-------|-----------|-----------------|
| **1. disabled_toolsets** | Per-profile config in `~/.hermes/profiles/<name>/config.yaml` | Prevents tenants from accessing delegation, code_execution, trading tools |
| **2. channel_prompts + channel_profiles** | Mapping in `~/.hermes/config.yaml` | Routes each Telegram user to their profile and system prompt, restricts behavior |
| **3. Linux users + iptables** | OS-level user isolation | Blocks tenant processes from localhost access, sandboxes to `/home/hermes-<name>/` |

Detailed in [`docs/03-constitution.md`](/docs/03-constitution.md) (Article IV).

## Bot Chain

```
User → @Apolaibot (free demo chat)
          │
          └── User clicks /upgrade → @Miropolbot (payment UI)
                    │
                    ├── Telegram Stars (instant, in-chat)
                    │     └── pre_checkout_query → OK
                    │     └── successful_payment → save to SQLite
                    │
                    └── TON via CryptoBot (external)
                          └── createInvoice → user pays in @CryptoBot
                          └── user clicks "I paid" → check_ton → activate
                    │
                    └── stars-activator.py (cron every 2 min)
                          └── Reads DB → `hermes-tenant onboard`
                          └── Creates: Linux user, profile, iptables, vault
                          └── Restarts Hermes gateway
```

## Deployment Layout

All paths are relative to `~/.hermes/` on the production server:

```
~/.hermes/
├── config.yaml              ← Main config: channel_profiles, channel_prompts
├── .env                     ← TELEGRAM_ALLOWED_USERS, global env
├── skills/                  ← Skill repository (source of truth)
│   └── <category>/<skill>/SKILL.md
├── config/
│   └── skill-tiers.yaml     ← Access tiers: base / admin_only / opt_in
├── profiles/
│   ├── poliakin/            ← Admin profile (full access)
│   ├── user_470549555/      ← Tenant profile
│   │   ├── config.yaml      ← Profile config (disabled_toolsets, sandbox)
│   │   ├── .env             ← Encrypted (age) environment
│   │   ├── .env.enc         ← Encrypted envelope
│   │   ├── skills/          ← Auto-synced base skills
│   │   ├── skills.local/    ← Tenant modifications (never overwritten)
│   │   ├── skills.imported/ ← Archive of skills promoted to base
│   │   └── memory/          ← Per-tenant memory
│   └── ... (one per tenant)
├── data/
│   └── stars_payments.db    ← SQLite payment database
├── scripts/                 ← Operational scripts (symlinked or copied)
├── keys/
│   └── hermes.key           ← Age encryption key
└── backups/
    └── offboarded/          ← Archived profiles on offboarding

/opt/hermes/
└── shared-skills/           ← Shared skill repository (mounted to tenants)

/home/
├── openclaw/                ← Admin user
├── hermes-ilya/             ← Tenant sandbox
│   ├── projects/
│   ├── scripts/
│   └── obsidian-vault/      ← Per-tenant knowledge base
└── hermes-<name>/...        ← More tenants
```

## Systemd Units

| Unit | Purpose |
|------|---------|
| `hermes-gateway.service` | Main Hermes gateway (production, ~200MB) |
| `apolaibot-demo.service` | Demo bot for trial users (~45MB) |
| `stars-payment.service` | Payment handler bot (~10MB) |

## Cron Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `stars-pro-activator` | Every 2 min | Check payment DB → onboard new Pro users |
| `canary-watch` | Every 12h | Health check (silent) |
| `cost-tracking pnl-morning` | Daily 09:00 | P&L report |
| `cost-tracking cost-weekly` | Monday 10:00 | Weekly cost report |
| `GitHub push` | Monday 10:00 | Auto-push to remote |
| `tenant-health-check` | (periodic) | Verify all tenants reachable |

## Key Architectural Decisions

1. **Demo = Option B** (lightweight script, not Hermes) — decided 16.06.2026. Do not revisit.
2. **Production = one Hermes gateway** — no separate instances per bot without sharding.
3. **Payments = Telegram Stars** — no external payment systems without explicit command.
4. **3-layer isolation** — disabled_toolsets + channel_prompts + Linux users. Never break this.
5. **No dashboard button** — admin accesses server via SSH only (security decision).
6. **Game gateway patch** — `gateway/run.py` has profile-specific `disabled_toolsets` patch. May be lost on Hermes update.

## Source References

| File | Role |
|------|------|
| `/docs/01-infrastructure.md` | Detailed infra doc (Russian) |
| `/docs/03-constitution.md` | Governance constitution |
| `/configs/tenant-config.yaml` | Example tenant profile config |
| `/scripts/hermes-tenant` | Tenant management CLI (496 lines) |

## Open Questions for Future Agents

- The gateway `disabled_toolsets` patch (`gateway/run.py`) is not version-controlled here. If Hermes upstream updates, the patch must be re-applied.
- Per-tenant cron isolation is not fully implemented — the cron tool doesn't pass profile context.
- Rate limiting (`rate_limiter.py`) exists but untested in production.
