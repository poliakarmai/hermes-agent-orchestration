# Configs & Data — Configuration Files and Data Models

This page documents all configuration files and SQLite database schemas used by the Hermes orchestration system.

## 1. Configuration Files

### hermes_config.py — ID Single Source of Truth

**Path:** `/hermes_config.py`

The only place where admin and unlimited user IDs are defined. All scripts import from here.

```python
# Reads from env with defaults:
# HERMES_ADMIN_IDS=5529208670,319665243
# HERMES_UNLIMITED_USERS=319665243,2115597720,470549555
ADMIN_IDS: set[int]       # Admin Telegram IDs
UNLIMITED_USERS: set[int] # Users exempt from rate limits
```

**Invariant:** Never hardcode IDs in individual scripts. Always `from hermes_config import ADMIN_IDS`.

### skill-tiers.yaml — Skill Access Control

**Path:** `/configs/skill-tiers.yaml`

Defines which skills are available to which tier of user. Three tiers:

| Tier | Behavior | Examples |
|------|----------|---------|
| `admin_only` | Admin only (Poliakarm) | bybit-trading, devops/*, mlops/*, red-teaming/godmode |
| `base` | Auto-synced to ALL tenants | communication-protocol, email-ops, github/*, productivity/* |
| `opt_in` | Tenant requests → admin installs | (currently empty in file) |

**Size:** ~67 admin_only skills, ~37 base skills (as of June 2026).

### tenant-config.yaml — Example Tenant Profile

**Path:** `/configs/tenant-config.yaml`

Example configuration for a tenant profile. Key sections:

```yaml
model:
  base_url: https://api.deepseek.com/v1
  default: deepseek-v4-pro
  provider: custom

agent:
  max_turns: 100
  gateway_timeout: 1200
  channel_prompt: "System prompt with sandbox description..."
  disabled_toolsets:
    - delegation
    - code_execution

profile:
  role: user
  shared_skills: /opt/hermes/shared-skills
  shared_instincts: /home/openclaw/.hermes/instincts
  sandbox: /home/hermes-<name>/
  tenant_name: <name>

platforms:
  telegram:
    home_channel: '<telegram_id>'

approvals:
  mode: always  # or auto / smart
```

The actual tenant profiles live at `~/.hermes/profiles/<name>/config.yaml` and are managed by `hermes-tenant`.

## 2. SQLite Database Schemas

### stars_payments.db — Payment & Subscription Data

**Location:** `~/.hermes/data/stars_payments.db`

```sql
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    telegram_username TEXT,
    amount_stars INTEGER NOT NULL,
    telegram_payment_id TEXT UNIQUE,
    status TEXT DEFAULT 'pending',
    expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE pro_users (
    telegram_id INTEGER PRIMARY KEY,
    telegram_username TEXT,
    activated_at TEXT,
    expires_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
```

**Used by:** `miropolbot.py` (write), `stars-activator.py` (read), `deprovision.py` (read+update)

### rate_limits.db — Rate Limit Counters

**Location:** `~/.hermes/data/rate_limits.db`

```sql
CREATE TABLE rate_limits (
    tg_id INTEGER NOT NULL,
    window_start INTEGER NOT NULL,
    window_type TEXT NOT NULL,  -- 'm' (minute) or 'h' (hour)
    count INTEGER DEFAULT 1,
    PRIMARY KEY (tg_id, window_start, window_type)
);

CREATE TABLE rate_config (
    tg_id INTEGER PRIMARY KEY,
    tier TEXT NOT NULL DEFAULT 'demo',
    rpm_override INTEGER,
    rph_override INTEGER
);
```

**Tiers:** demo (30 RPM / 500 RPH / 1M TPM), pro (60/2000/5M), admin (120/5000/unlimited)

**Used by:** `rate_limiter.py` (library), `tenant-rate-watch.py` (monitoring)

### tenant_metrics.db — Hourly Aggregated Metrics

**Location:** `~/.hermes/data/tenant_metrics.db`

```sql
CREATE TABLE metrics_hourly (
    tg_id INTEGER NOT NULL,
    hour TEXT NOT NULL,  -- 'YYYY-MM-DD HH:00'
    requests INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    total_latency REAL DEFAULT 0.0,
    latency_samples INTEGER DEFAULT 0,
    PRIMARY KEY (tg_id, hour)
);
```

**Used by:** `metrics-collector.py` (write), `generate-tenant-dashboard.py` (read)

### tenant_audit.db — Audit Trail

**Location:** `~/.hermes/data/tenant_audit.db`

Schema defined in `tenant-audit.py`. Logs actions performed by tenants for security and compliance.

**Used by:** `tenant-audit.py` (write), `audit-log-parser.py` (analysis)

## 3. Data Flow Summary

```
Config Files (source of truth)
  ├── hermes_config.py → environment → all scripts
  ├── skill-tiers.yaml → skill-sync.py → tenant profiles
  ├── tenant-config.yaml (template) → hermes-tenant → tenant profiles
  └── config.yaml (gateway) → hermes-gateway → runtime isolation

SQLite Databases (runtime state)
  ├── stars_payments.db ← miropolbot.py → stars-activator.py / deprovision.py
  ├── rate_limits.db ← rate_limiter.py (check/record) → tenant-rate-watch.py
  ├── tenant_metrics.db ← metrics-collector.py → generate-tenant-dashboard.py
  └── tenant_audit.db ← tenant-audit.py → audit-log-parser.py
```

## Source Map

| File | Role |
|------|------|
| `/hermes_config.py` | SSOT for admin/unlimited user IDs |
| `/configs/skill-tiers.yaml` | Skill access tiers definition |
| `/configs/tenant-config.yaml` | Example tenant profile config |
| `~/.hermes/config.yaml` | Main Hermes gateway config (not in repo) |
| `~/.hermes/data/stars_payments.db` | Payment and subscription database |
| `~/.hermes/data/rate_limits.db` | Rate limit counters database |
| `~/.hermes/data/tenant_metrics.db` | Aggregated metrics database |
| `~/.hermes/data/tenant_audit.db` | Audit trail database |
