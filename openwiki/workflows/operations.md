# Operations

This document covers operational commands, cron jobs, security mechanisms, and maintenance procedures.

## CLI Tools

### hermes-tenant — Tenant Management

**File:** `/scripts/hermes-tenant` (496 lines)

```bash
# List all tenants and their status
hermes-tenant list

# Onboard new tenant (creates Linux user, profile, iptables, vault)
hermes-tenant onboard --tg-id=123456789 --name=username

# Offboard tenant (backup, delete, remove iptables)
hermes-tenant offboard --tg-id=123456789
```

**Key behaviors:**
- Admin user (poliakarm) skips Linux user creation
- Onboarding auto-encrypts `.env` with age if key is available
- Onboarding auto-updates `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env`
- Offboarding creates a timestamped backup in `~/.hermes/backups/offboarded/`
- iptables isolation blocks localhost (127.0.0.0/8) per tenant UID, allows DNS (UDP/53)

### skill-sync.py — Skill Distribution

**File:** `/scripts/skill-sync.py`

```bash
# Sync base skills to all tenants
python3 scripts/skill-sync.py

# Preview only
python3 scripts/skill-sync.py --dry-run

# Show all tenants' skill status
python3 scripts/skill-sync.py --status

# Install opt-in skill for specific tenant
python3 scripts/skill-sync.py --install <skill> --tenant <name>

# Remove opt-in skill
python3 scripts/skill-sync.py --install <skill> --tenant <name> --remove

# Discover tenant-local skills (pull request flow)
python3 scripts/skill-sync.py --pull --tenant <name>
python3 scripts/skill-sync.py --pull --tenant <name> --dry-run

# Import tenant skill into base (after review)
python3 scripts/skill-sync.py --import <skill> --tenant <name>
```

**Skill tiers** (from `configs/skill-tiers.yaml`):
| Tier | Access | Count |
|------|--------|-------|
| `admin_only` | Only Poliakarm (admin) | ~65 skills |
| `base` | Auto-synced to ALL tenants | ~41 skills |
| `opt_in` | Tenant requests → admin installs | ~26 skills |

The 3-stage review pipeline for tenant-submitted skills:
1. **Security scan** (`skill-security-scan.py`) — blocks on CRITICAL findings
2. **Judge review** (DeepSeek API) — checks constitution compliance
3. **Adversarial review** (independent model) — checks hallucinations, safety

## Cron Jobs

Configured in Hermes gateway (not in this repo's crontab):

| Job | Schedule | Description |
|-----|----------|-------------|
| `stars-pro-activator` | Every 2 min | Check payment DB, onboard new Pro users, restart gateway |
| `canary-watch` | Every 12h | Silent health check |
| `pnl-morning` | Daily 09:00 | Bybit P&L report |
| `cost-weekly` | Monday 10:00 | Weekly cost tracking |
| `github-push` | Monday 10:00 | Auto-push to remote |
| `tenant-health-check` | Periodic | Verify tenant availability |

**Important:** Cron tool does not properly pass profile context — per-tenant cron isolation is not fully implemented.

## Systemd Services

| Service | RAM | Type | Restart |
|---------|-----|------|---------|
| `hermes-gateway.service` | ~200MB | main gateway | On-failure + manual |
| `apolaibot-demo.service` | ~45MB | demo bot | On-failure |
| `stars-payment.service` | ~10MB | payment handler | On-failure |

Gateway restart takes 3+ minutes (graceful shutdown). Use `systemctl --user restart hermes-gateway`.

## Security Mechanisms

### Three-Layer Isolation (Critical — do not modify without understanding)

See full details in [Architecture Overview](../architecture/overview.md#three-layer-isolation).

1. **disabled_toolsets** — per-profile config (no delegation, code_execution for tenants)
2. **channel_prompts + channel_profiles** — config.yaml routing per Telegram user
3. **Linux users + iptables** — filesystem + network isolation

### Age Encryption

`.env` files (containing bot tokens) are encrypted with `age`:
- Key: `~/.hermes/keys/hermes.key`
- Output: `<profile>/.env.enc` (chmod 600)
- Performed automatically during `hermes-tenant onboard`

### Input Sanitization (Demo Bot)

8 prompt injection regex patterns block:
- "ignore previous instructions"
- "you are now DAN/STAN/jailbreak"
- "pretend to be"
- "new system prompt"
- "forget everything"
- "developer mode"
- "override system/safety/instructions"

### Gateway Patch

The Hermes gateway `gateway/run.py` has a profile-specific `disabled_toolsets` patch. This is NOT version-controlled in this repo and may be lost on Hermes upgrade.

### SSH-Only Dashboard

The dashboard button was removed — admin accesses server exclusively via SSH.

## Maintenance Procedures

### Disk Cleanup

As of the June 2026 audit, disk usage was reduced from 84% to 73% by cleaning:
- Miniconda3 (removed unused environments)
- pip cache
- SQLite WAL files

Target: automated cache cleanup + VACUUM + Whisper→Groq API migration (−5GB).

### Adding New Skills to Base

```bash
# Edit tiers file
# Add skill path under 'base:' in configs/skill-tiers.yaml

# Run sync to distribute
python3 scripts/skill-sync.py

# Verify tenant received it
python3 scripts/skill-sync.py --status
```

### Promoting Tenant Skill to Base

```bash
# Step 1: Discover tenant modifications
python3 scripts/skill-sync.py --pull --tenant user_<tg_id>

# Step 2: Review passes (security → judge → adversarial)

# Step 3: Import to base
python3 scripts/skill-sync.py --import <skill> --tenant user_<tg_id>
# Automatically synced to all tenants
```

## Monitoring

The June 2026 audit discovered and resolved:
- 61 cron jobs reviewed (7 optimized, −67% runs)
- Watchdogs (bybit + telegram) disabled (systemd duplicates)
- MCP `get_metrics` fix (date vs first_record)
- Streaming enabled (`streaming: true`)
- Whisper fix (sys.path fallback for voice messages)

## Invariants (from AGENTS.md)

1. **One gateway — two roles.** Do not create separate gateway instances for bots.
2. **Isolation through profiles.** Tenants never see each other's skills/memory/crons.
3. **Permissions through channel_profiles.** Never patch bot code for access control.
4. **All production configs in YAML.** Source of truth: `~/.hermes/config.yaml`.
5. **Judge before commit.** Mandatory review for all code/config changes.

## Known Technical Debt

1. Gateway `disabled_toolsets` patch not in version control — may be lost on update
2. Per-tenant cron isolation incomplete
3. `rate_limiter.py` exists but untested in production
4. No automated test suite for scripts
5. No CI/CD pipeline
