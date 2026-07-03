# Hermes Orchestration — Quickstart

**Repository:** `hermes-orchestration` (private: `poliakarmai/hermes-agent-orchestration`)  
**Primary language:** Python 3.11+  
**Config format:** YAML  
**Documentation language:** Russian (production docs), English (code)

## Overview

This repository is the **configuration and orchestration layer** for a multi-tenant AI-agent platform called **Hermes**. It manages:

- **Multi-tenant AI agent infrastructure** — one Hermes gateway serving multiple isolated tenants
- **Telegram bots** — demo bot, payment bot, and the main Hermes gateway bot
- **Skill distribution system** — tier-based skill synchronization across tenants
- **Payment & activation pipeline** — Telegram Stars and TON (CryptoBot) payment → auto-onboarding
- **Tenant lifecycle management** — CLI-based onboarding and offboarding with Linux-level isolation

The system is **production-deployed** with real paying tenants. As of June 2026, there are 5+ active tenants.

## Repository Structure

```
hermes-orchestration/
├── bots/
│   ├── apolaibot-demo.py      # Demo bot (@Apolaibot) — lightweight Python script
│   └── miropolbot.py          # Payment handler (@Miropolbot) — Stars + TON
├── configs/
│   ├── tenant-config.yaml     # Example tenant profile configuration
│   └── skill-tiers.yaml       # Skill access tiers (base / admin_only / opt_in)
├── scripts/
│   ├── skill-sync.py          # Two-way skill synchronization engine
│   ├── stars-activator.py     # Cron-based Pro subscription activator
│   └── hermes-tenant          # CLI for tenant onboarding/offboarding/list
├── docs/
│   ├── 01-infrastructure.md   # Infrastructure architecture & bot chain
│   ├── 02-skill-sync.md       # Skill Sync v3 design & review pipeline
│   ├── 03-constitution.md     # Hermes governance constitution
│   ├── 05-onboarding-checklist.md  # Tenant onboarding checklist
│   └── 06-roadmap.md          # Development roadmap & audit log
├── AGENTS.md                  # AI-agent navigation file (Russian)
├── CLAUDE.md                  # Claude agent instructions (references AGENTS.md)
└── README.md                  # Migration notice (moved to hermes-agent-orchestration)
```

## Quickstart Commands

```bash
# Skill synchronization (distribute base skills to all tenants)
python3 scripts/skill-sync.py

# Preview sync changes without applying
python3 scripts/skill-sync.py --dry-run

# Check tenant status
python3 scripts/skill-sync.py --status

# Tenant management CLI
python3 scripts/hermes-tenant list
python3 scripts/hermes-tenant onboard --tg-id=123 --name=username
python3 scripts/hermes-tenant offboard --tg-id=123

# Payment activation (runs via cron every 2 minutes)
python3 scripts/stars-activator.py

# Run demo bot directly (requires ~/.hermes/profiles/demo/.env)
python3 bots/apolaibot-demo.py

# Run payment handler directly (requires STARS_BOT_TOKEN env)
python3 bots/miropolbot.py
```

## Architecture at a Glance

```
User → @Apolaibot (demo, ~45MB RAM)
          └── /upgrade → @Miropolbot (payment, ~10MB RAM)
                              └── Payment confirmed → stars-activator (cron 2min)
                                    └── hermes-tenant onboard
                                          └── @Morearbot (Hermes gateway, ~200MB RAM, full Pro)
```

The system uses **one Hermes gateway process** for all production tenants. Isolation is achieved through three layers:

1. **disabled_toolsets** — per-profile tool restrictions (e.g., no trading for tenants)
2. **channel_prompts + channel_profiles** — config.yaml routing per Telegram user
3. **Linux users + iptables** — filesystem and network isolation

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Tenant** | An isolated user environment with its own Linux user, Hermes profile, skill set, and Obsidian vault |
| **Skill Tiers** | `base` (auto-synced to all), `admin_only` (admin only), `opt_in` (tenant requests → admin installs) |
| **Skill Sync v3** | Two-way sync with 3-stage review (security scan → Judge → adversarial) |
| **Profile** | Per-tenant config under `~/.hermes/profiles/user_<tg_id>/` |
| **Channel routing** | `channel_profiles` in `config.yaml` maps Telegram user IDs to profiles |

## Documentation Map

| Page | Contents |
|------|----------|
| [Architecture Overview](architecture/overview.md) | Multi-tenant architecture, isolation layers, bot chain, deployment |
| [Bots](domain/bots.md) | @Apolaibot, @Miropolbot, @Morearbot — purpose, code, lifecycle |
| [Data Models](domain/data-models.md) | Config structures, skill tiers, payment DB schema |
| [Tenant Lifecycle](workflows/tenant-lifecycle.md) | Onboarding, offboarding, payment → activation pipeline |
| [Operations](workflows/operations.md) | Commands, cron, systemd, security, invariants |

## Important Invariants

From [`AGENTS.md`](/AGENTS.md) and [`docs/03-constitution.md`](/docs/03-constitution.md):

1. **One gateway, two roles.** Do not create separate gateway instances per bot.
2. **Isolation through profiles.** Tenants do not see each other's skills, memory, or crons.
3. **Permissions through channel_profiles.** Do not patch bot code for access control.
4. **Three isolation layers.** disabled_toolsets + channel_prompts + Linux users. Never break this.
5. **Judge before commit.** All code/config changes require mandatory Judge review.
6. **Age encryption for .env files.** API keys never exposed in responses.

## Migration Note

This repository is currently merged into **hermes-agent-orchestration** at GitHub. The canonical location is `~/projects/hermes-agent-orchestration/`. This repo (`hermes-orchestration`) remains as the local working copy of configuration and scripts.
