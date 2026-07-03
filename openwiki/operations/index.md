# Operations — CLI Tools, Cron, and Configuration

This page covers the operational side of Hermes agent orchestration: CLI tools, environment configuration, cron jobs, and server management details.

## 1. hermes-tenant CLI

**File:** `/scripts/hermes-tenant`

The primary CLI for tenant lifecycle management. Written in Python, 496 lines.

### Commands

```bash
# Onboard a new tenant
python3 scripts/hermes-tenant onboard --tg-id <telegram_user_id> --name <short_name>

# Offboard (remove) a tenant
python3 scripts/hermes-tenant offboard --tg-id <telegram_user_id>

# List all tenants
python3 scripts/hermes-tenant list
```

### Onboard Steps (automated)

1. Loads tenant config template from `scripts/` directory
2. Creates Linux user `hermes-<name>` with home directory
3. Creates `~/.hermes/profiles/<name>/` with `.env` and `config.yaml`
4. Encrypts `.env` with age (`age-encrypt`, key at `~/.hermes/keys/hermes.key`)
5. Sets up iptables rules for network isolation
6. Creates Obsidian vault at `~/.hermes/profiles/<name>/vault/`
7. Updates `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env`
8. Adds `channel_profiles` + `channel_prompts` to `config.yaml`
9. Syncs base skills to the new profile
10. Restarts `hermes-gateway.service`

### Offboard Steps

1. Removes `channel_profiles`/`channel_prompts` entries from `config.yaml`
2. Removes tg_id from `TELEGRAM_ALLOWED_USERS`
3. Removes Linux user (`userdel -r hermes-<name>`)
4. Removes iptables rules
5. Removes profile directory
6. Restarts `hermes-gateway.service`

## 2. Environment Configuration

### hermes_config.py (SSOT)

**File:** `/hermes_config.py`

Single source of truth for admin and unlimited user IDs. Reads from environment variables.

```python
# Environment variables and their defaults:
# HERMES_ADMIN_IDS — comma-separated Telegram IDs of admins
#   Default: "5529208670,319665243"
# HERMES_UNLIMITED_USERS — comma-separated Telegram IDs with no rate limits
#   Default: "319665243,2115597720,470549555"

# Always import instead of hardcoding IDs:
from hermes_config import ADMIN_IDS, UNLIMITED_USERS
```

**Invariant:** Every script that needs admin/user IDs must import from `hermes_config.py`. Never hardcode IDs.

### Rate Limit Configuration

Rate limits are configurable via `HERMES_TIER_LIMITS` env var (JSON format), or fall back to defaults:

| Tier | RPM | RPH | TPM (monthly token budget) |
|------|-----|-----|---------------------------|
| demo | 30 | 500 | 1,000,000 |
| pro | 60 | 2,000 | 5,000,000 |
| admin | 120 | 5,000 | 0 (unlimited) |

**Database:** `~/.hermes/data/rate_limits.db` (SQLite)

## 3. Cron Jobs

All cron jobs run with `no_agent` flag — stdout is the delivery channel. **Silent when OK, alert when broken.**

| Frequency | Script | Function |
|-----------|--------|----------|
| Every 2 min | `stars-activator.py` | Check pending payments in `stars_payments.db` → `hermes-tenant onboard` for unpaid confirmed payments |
| Every 5 min | `metrics-collector.py` | Collect metrics from gateway logs, rate_limits, and audit DB |
| Every 5 min | `generate-tenant-dashboard.py` | Rebuild `~/.hermes/data/dashboard.html` |
| Every 10-15 min | `tenant-rate-watch.py` | Check rate limit usage; alert admin if > 80% for any tenant |
| Every 30 min | `deprovision.py` | Check for expired Pro subscriptions → `hermes-tenant offboard` |
| Daily 02:00 | `tenant-backup.py` | Backup profiles + config + payments DB; keep 7 days |
| Daily 12:00 | Canary-watch (cron in Hermes) | Health check, silent |
| Weekly Mon 10:00 | GitHub push (cron) | Push to GitHub |

### Critical cron script rules

- All cron script paths should be `~/.hermes/scripts/` (or `~/.local/bin/` as fallback)
- Cron scripts never call `send_alert()` or `hermes send` — stdout goes to the channel
- Keep "silent when OK" discipline

## 4. Systemd Services

All services are user-level systemd units in `~/.config/systemd/user/`.

```bash
# Check service status
systemctl --user status apolaibot-demo.service
systemctl --user status miropolbot.service
systemctl --user status hermes-gateway.service

# Restart gateway (3+ min delay due to graceful shutdown)
systemctl --user restart hermes-gateway.service
systemctl --user status hermes-gateway.service | grep Active

# View logs
journalctl --user -u hermes-gateway.service -n 100 -f
```

### Resource Limits (from commit 69fd51c)

- MemoryMax, CPUQuota, TasksMax set on all 3 services
- Budget: `max_concurrent_sessions: 3`, `cron.max_parallel_jobs: 3` for DeepSeek throttling

## 5. Data Locations

| Path | Contents |
|------|----------|
| `~/.hermes/config.yaml` | Main Hermes gateway config (channel_profiles, channel_prompts) |
| `~/.hermes/.env` | Gateway environment variables (age-encrypted) |
| `~/.hermes/data/stars_payments.db` | Payment and subscription SQLite DB |
| `~/.hermes/data/rate_limits.db` | Rate limit counters SQLite DB |
| `~/.hermes/data/tenant_metrics.db` | Hourly metrics SQLite DB |
| `~/.hermes/data/tenant_audit.db` | Audit trail SQLite DB |
| `~/.hermes/data/dashboard.html` | Live tenant dashboard (auto-refresh 30s) |
| `~/.hermes/backups/daily/` | Daily tarball backups (7-day rotation) |
| `~/.hermes/profiles/<name>/` | Per-tenant profile: config, skills, vault, .env |
| `~/.hermes/skills/` | Base skills source of truth |
| `~/.hermes/config/skill-tiers.yaml` | Skill access tiers |
| `~/.hermes/keys/hermes.key` | Age encryption key (chmod 600) |

## 6. Security Notes

- **Age encryption** for all `.env` files — key at `~/.hermes/keys/hermes.key` (permissions 600)
- `approvals.mode: auto` — no manual approval needed for low-risk commands (set in commit 7aa5dc0 era)
- **iptables isolation** per tenant — creates separate network namespace
- **Cross-model review** — all critical changes reviewed by Qwen + Nemotron ($0/month) — see docs/06-roadmap.md

## Source Map

| File | Purpose |
|------|---------|
| `scripts/hermes-tenant` | Tenant lifecycle CLI (onboard/offboard/list) |
| `scripts/rate_limiter.py` | Per-tenant rate limiting library |
| `scripts/stars-activator.py` | Payment activation cron |
| `scripts/deprovision.py` | Expired subscription cron |
| `scripts/metrics-collector.py` | Metrics aggregation cron |
| `scripts/generate-tenant-dashboard.py` | Dashboard HTML generator |
| `scripts/tenant-rate-watch.py` | Rate limit watchdog |
| `scripts/tenant-backup.py` | Daily backup script |
| `scripts/tenant-audit.py` | Audit trail recorder |
| `scripts/audit-log-parser.py` | Audit log analyzer |
| `hermes_config.py` | SSOT: admin/user ID configuration |
