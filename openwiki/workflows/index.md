# Workflows — Key Operational Processes

This page documents the major workflows in the Hermes agent orchestration system.

## 1. Tenant Payment & Onboarding Flow

This is the primary user acquisition pipeline: free demo → Stars payment → Pro activation.

```
User → @Apolaibot (free chat) → /upgrade → @miropolbot

Payment flow (miropolbot.py):
  1. User sends /start to @miropolbot
  2. Bot sends Telegram Stars invoice for 100 ⭐ (30 days Pro)
  3. User pays → Telegram sends successful_payment webhook
  4. miropolbot saves payment to stars_payments.db (SQLite)
  5. miropolbot notifies user: "Write /start in @Morearbot"
  6. Admin receives "🎉 New Pro client!" alert
  7. stars-activator.py (cron, every 2 min) detects pending payment
  8. Runs: hermes-tenant onboard --tg-id <id> --name <name>
  9. Restarts hermes-gateway.service
  10. User can now chat with @Morearbot (Pro gateway)
```

**Key files:** `/bots/miropolbot.py`, `/scripts/stars-activator.py`, `/scripts/hermes-tenant`

**Onboarding steps executed by `hermes-tenant onboard`:**
- Creates Linux user `hermes-<name>` with uid and home
- Creates profile directory with `.env` + `config.yaml`
- Encrypts `.env` with age
- Sets up iptables rules for network isolation
- Creates per-tenant Obsidian vault for memory
- Adds telegram_id to `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env`
- Adds `channel_profiles` + `channel_prompts` entries to `config.yaml`
- Syncs base skills to the new tenant

**Critical check after onboarding (from docs/05-onboarding-checklist.md):**
1. `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env` — must include new tg_id
2. `channel_profiles` in `config.yaml` — mapping tg_id → profile
3. `channel_prompts` in `config.yaml` — system prompt for tg_id
4. Restart: `systemctl --user restart hermes-gateway` (takes 3+ min — graceful shutdown)

## 2. Deprovisioning (Expired Subscription)

```
deprovision.py (cron, every 30 min):
  1. Query stars_payments.db pro_users for expired subscriptions
  2. For each expired user:
     a. hermes-tenant offboard --tg-id <id>
     b. Notify admin: "Tenant <name> deactivated"
     c. Notify user via Telegram

hermes-tenant offboard steps:
  - Remove channel_profiles/channel_prompts from config.yaml
  - Remove tg_id from TELEGRAM_ALLOWED_USERS
  - Remove Linux user and home directory
  - Remove iptables rules
  - Remove Obsidian vault
  - Restart hermes-gateway.service
```

**Key files:** `/scripts/deprovision.py`, `/scripts/hermes-tenant`

## 3. Skill Sync v3 (Two-Way Distribution)

### Sync Direction 1: Base → All Tenants

```
Admin skills (~/.hermes/skills/) ← source of truth
  → skill-sync.py
  → Each tenant's ~/.hermes/profiles/<name>/skills/
```

- **Base skills** (defined in `configs/skill-tiers.yaml` under `base:`) are auto-synced to ALL tenants
- **admin_only skills** — never synced to tenants (trading, devops, ML ops, etc.)
- **opt_in skills** — installed per-tenant via `--install`

### Sync Direction 2: Tenant → Base (Pull & Import)

```
Tenant develops a skill in ~/.hermes/profiles/<name>/skills.local/
  → skill-sync.py --pull --tenant <name>
  → Three-stage review pipeline
  → skill-sync.py --import <skill> --tenant <name>
  → Skill becomes base → synced to all tenants
```

### Three-Stage Review Pipeline

| Stage | Tool | What It Checks | Blocking Criteria |
|-------|------|----------------|-------------------|
| **1. Security** | `skill-security-scan.py` | Injections, dangerous commands, YAML validity | CRITICAL findings |
| **2. Judge** | DeepSeek API (`~/.local/bin/judge`) | Constitution compliance, perimeter safety | `passed: false` |
| **3. Adversarial** | DeepSeek API (second model) | Contradictions, hallucinations, multi-tenant safety | `approved: false` |

**Key files:** `/scripts/skill-sync.py`, `/scripts/skill-validate.py`

## 4. Monitoring & Operations Workflow

### Metrics Collection
- `metrics-collector.py` (cron, every 5 min) — reads gateway logs, rate limit DB, audit DB
- Writes to `~/.hermes/data/tenant_metrics.db` (hourly aggregates: requests, errors, avg latency)

### Dashboard Generation
- `generate-tenant-dashboard.py` (cron, every 5 min) — generates HTML dashboard
- Output: `~/.hermes/data/dashboard.html`
- Auto-refreshes every 30 seconds
- Shows per-tenant: tier, rate usage, subscription status, requests, errors

### Rate Limit Monitoring
- `tenant-rate-watch.py` (cron, every 10-15 min) — checks rate limit usage
- Alerts admin if any tenant exceeds 80% of their rate limit
- Tiers: demo (30 RPM/500 RPH/1M TPM), pro (60/2000/5M), admin (120/5000/unlimited)

### Backup
- `tenant-backup.py` (cron, daily 02:00) — tarballs all profiles + config + payments DB
- 7-day rotation

### Audit Trail
- `tenant-audit.py` — logs tenant actions to `~/.hermes/data/tenant_audit.db`
- `audit-log-parser.py` — query and analyze audit logs

## 5. Cron Job Change Protocol

Rules established in `/docs/05-onboarding-checklist.md`:
- `no_agent` scripts: stdout = delivery channel; never call `send_alert()` or `hermes send`
- Use `~/.hermes/scripts/` paths (check both paths if script in `~/.local/bin/`)
- **Silent when OK, alert when broken** — no spam when everything works

## Source Map

| File | Workflow Role |
|------|---------------|
| `bots/miropolbot.py` | Stars payment handler (long-polling) |
| `scripts/stars-activator.py` | Cron: pending payment → tenant creation |
| `scripts/deprovision.py` | Cron: expired subscription → tenant removal |
| `scripts/hermes-tenant` | CLI: onboard/offboard/list tenant operations |
| `scripts/skill-sync.py` | Two-way skill sync engine |
| `scripts/skill-validate.py` | Stage 0 CI/CD skill validation |
| `scripts/rate_limiter.py` | Library: per-tenant request/token rate limiting |
| `scripts/tenant-rate-watch.py` | Cron: rate limit threshold alerting |
| `scripts/metrics-collector.py` | Cron: hourly metric aggregation |
| `scripts/generate-tenant-dashboard.py` | Cron: HTML dashboard builder |
| `scripts/tenant-audit.py` | Audit trail recording |
| `scripts/audit-log-parser.py` | Audit log analysis |
| `scripts/tenant-backup.py` | Daily backup with rotation |
