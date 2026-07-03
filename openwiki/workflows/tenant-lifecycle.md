# Tenant Lifecycle

This document describes the complete lifecycle of a Hermes tenant — from payment through onboarding, daily operation, to offboarding.

## Lifecycle Flow

```
Payment received
    → stars-activator (cron, 2min)
        → hermes-tenant onboard
            → 1. Create Linux user (hermes-<name>)
            → 2. Setup iptables isolation
            → 3. Create Hermes profile (config.yaml, .env)
            → 4. Add to channel_profiles + channel_prompts
            → 5. Add to TELEGRAM_ALLOWED_USERS
            → 6. Create Obsidian vault
            → 7. Set sandbox permissions
            → 8. Restart Hermes gateway
                → User can chat with @Morearbot
```

## Step-by-Step: Onboarding

### Trigger

The `stars-activator.py` script runs every 2 minutes via cron. It queries the payments database for `payments.status = 'confirmed'` where no corresponding `pro_users` entry exists.

### CLI Command

```bash
hermes-tenant onboard --tg-id=319665243 --name=poliakarm
```

For admin users (poliakarm), the Linux user creation step is skipped.

### What Happens

1. **Linux user created:** `sudo useradd -m -s /bin/bash hermes-<name>` → sandbox at `/home/hermes-<name>/`
2. **iptables rules added:** Block localhost access, allow DNS (UDP/53)
3. **Profile directory created:** `~/.hermes/profiles/user_<tg_id>/`
4. **config.yaml written:** Profile config with disabled toolsets, sandbox path, tenant name
5. **.env created:** Populated with the global TELEGRAM_BOT_TOKEN, then encrypted with age
6. **Gateway config updated:**
   - `channel_profiles[tg_id] = user_<tg_id>`
   - `channel_prompts[tg_id]` = per-tenant system prompt with sandbox + restrictions
   - `TELEGRAM_ALLOWED_USERS` updated
7. **Obsidian vault created:** `/home/hermes-<name>/obsidian-vault/` with welcome notes
8. **Sandbox permissions set:** `chown hermes-<name>:openclaw` with `chmod 770`
9. **Gateway restarted** (by `stars-activator.py`): `systemctl --user restart hermes-gateway`

### Post-Onboarding Checklist

See full details in `/docs/05-onboarding-checklist.md`:

- [ ] Linux user exists: `id hermes-<name>`
- [ ] iptables rules active: `sudo iptables -L OUTPUT -n | grep "owner UID match <uid>"`
- [ ] Sandbox permissions: `stat -c '%a %U:%G' /home/hermes-<name>/` → 770
- [ ] Obsidian vault exists: `/home/hermes-<name>/obsidian-vault/`
- [ ] Age encryption: `.env.enc` present in profile
- [ ] Skill sync: `python3 ~/.hermes/scripts/skill-sync.py --tenant user_<tg_id>`
- [ ] disabled_toolsets: `delegation, code_execution`
- [ ] Gateway accepts user (not "Unauthorized user")

## Payment → Activation Pipeline

```
1. User pays in @Miropolbot (Stars or TON)
2. Payment saved to SQLite payments table (status='confirmed')
3. stars-activator.py detects new confirmed payment (cron, 2min)
4. Calls hermes-tenant onboard
5. DB updated: payments.status='activated', pro_users row inserted
6. Gateway restarted
7. User can now chat in @Morearbot
```

### Database Schema

```sql
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    telegram_username TEXT,
    amount_stars INTEGER NOT NULL,
    telegram_payment_id TEXT UNIQUE,
    status TEXT DEFAULT 'pending',       -- pending → confirmed → activated | failed
    expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE pro_users (
    telegram_id INTEGER PRIMARY KEY,
    telegram_username TEXT,
    activated_at TEXT,
    expires_at TEXT NOT NULL,            -- 30 days from activation
    active INTEGER DEFAULT 1
);
```

Subscription duration: **30 days** from activation.

## Step-by-Step: Offboarding

```bash
hermes-tenant offboard --tg-id=319665243
```

1. Remove from `channel_profiles` and `channel_prompts` in `~/.hermes/config.yaml`
2. Remove from `TELEGRAM_ALLOWED_USERS`
3. Backup profile to `~/.hermes/backups/offboarded/`
4. Delete profile directory
5. Remove iptables rules
6. Delete Linux user: `sudo userdel -r hermes-<name>`
7. Restart gateway (manual step)

## Skill Sync on Tenant Change

After onboarding or offboarding, skill synchronization ensures the tenant has the correct skill set:

```bash
# Sync base skills to all tenants
python3 scripts/skill-sync.py

# Sync to specific tenant only
python3 scripts/skill-sync.py --install <skill> --tenant user_<tg_id>
```

## Source References

| Step | Script | Key Function |
|------|--------|-------------|
| Activation trigger | `/scripts/stars-activator.py` | `main()` — reads DB, calls onboard |
| Onboarding | `/scripts/hermes-tenant` | `onboard()` — full lifecycle |
| Offboarding | `/scripts/hermes-tenant` | `offboard()` — cleanup |
| Skill sync | `/scripts/skill-sync.py` | `sync_base()` — distribute skills |

## Change Guidance

When modifying the tenant lifecycle:

1. **stars-activator.py** is cron-based and must remain idempotent. If it fails mid-way (e.g., onboard fails), the DB should not mark as activated without actual profile creation.
2. **hermes-tenant** creates Linux users with `sudo`. Test with `--dry-run` equivalents when possible (none exist yet — consider adding).
3. **iptables rules** persist across reboots. On offboarding, rules must be cleaned up.
4. **Gateway restart** is heavy (~3+ min for graceful shutdown). Batch multiple activations before restarting.
5. **New tenants** need their TELEGRAM_BOT_TOKEN manually set in `.env` unless using the system token.
