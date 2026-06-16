#!/usr/bin/env python3
"""
Tenant Dashboard Generator — генерирует HTML-дашборд всех тенантов.
Запускается по cron (рекомендуется раз в 5 минут).
Вывод: ~/.hermes/data/dashboard.html
"""
import os
import sys
import sqlite3
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
CONFIG_YAML = HERMES_HOME / "config.yaml"
PROFILES_DIR = HERMES_HOME / "profiles"
STARS_DB = HERMES_HOME / "data" / "stars_payments.db"
RATE_DB = HERMES_HOME / "data" / "rate_limits.db"
DASHBOARD_PATH = HERMES_HOME / "data" / "dashboard.html"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>Aegis AI Engine — Tenant Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
h1 { color: #38bdf8; margin-bottom: 8px; }
.timestamp { color: #64748b; font-size: 14px; margin-bottom: 24px; }
.card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #38bdf8; }
.card.pro { border-left-color: #22c55e; }
.card.demo { border-left-color: #64748b; }
.card.expired { border-left-color: #ef4444; opacity: 0.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-header .name { font-size: 18px; font-weight: 600; }
.card-header .badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.badge-pro { background: #22c55e22; color: #22c55e; }
.badge-demo { background: #64748b22; color: #64748b; }
.badge-expired { background: #ef444422; color: #ef4444; }
.badge-admin { background: #a855f722; color: #a855f7; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.metric { background: #0f172a; border-radius: 8px; padding: 8px 12px; }
.metric-label { font-size: 11px; color: #64748b; text-transform: uppercase; }
.metric-value { font-size: 16px; font-weight: 600; margin-top: 2px; }
.metric-value.warn { color: #f59e0b; }
.metric-value.danger { color: #ef4444; }
.metric-value.ok { color: #22c55e; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 24px; }
.summary-card { background: #1e293b; border-radius: 12px; padding: 16px; text-align: center; }
.summary-card .number { font-size: 32px; font-weight: 700; }
.summary-card .label { font-size: 14px; color: #64748b; margin-top: 4px; }
</style>
</head>
<body>
<h1>🚀 Aegis AI Engine — Tenants</h1>
<p class="timestamp">Обновлено: {timestamp} | Автообновление: 30 сек</p>

<div class="summary">
{summary_cards}
</div>

{tenant_cards}

</body>
</html>"""


def load_yaml(path):
    """Simple YAML loader для нашего конфига (без зависимости от PyYAML)."""
    data = {}
    if not path.exists():
        return data

    current_key = None
    current_dict = data
    stack = [(0, data)]

    with open(path) as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.startswith('#'):
                continue

            indent = len(line) - len(line.lstrip())
            if stripped.startswith('- '):
                value = stripped[2:].strip().strip('"').strip("'")
                if isinstance(current_dict, dict):
                    lst_key = [k for k in current_dict if isinstance(current_dict[k], list)]
                    if lst_key:
                        current_dict[lst_key[-1]].append(value)
                continue

            if ':' in stripped:
                key, _, val = stripped.partition(':')
                key = key.strip().strip('"').strip("'")
                val = val.strip().strip('"').strip("'")

                while stack and stack[-1][0] >= indent:
                    stack.pop()
                    current_dict = stack[-1][1] if stack else data

                if val:
                    current_dict[key] = val
                else:
                    current_dict[key] = {}
                    current_dict = current_dict[key]
                    stack.append((indent, current_dict))

    return data


def get_tenant_list():
    """Возвращает список тенантов из config.yaml."""
    cfg = load_yaml(CONFIG_YAML)
    profiles_map = cfg.get("telegram", {}).get("channel_profiles", {})
    tenants = []

    for tg_id, profile_name in profiles_map.items():
        tg_id = int(tg_id)
        if profile_name == "poliakarm":
            continue

        profile_dir = PROFILES_DIR / profile_name
        pcfg = load_yaml(profile_dir / "config.yaml") if (profile_dir / "config.yaml").exists() else {}
        name = pcfg.get("profile", {}).get("tenant_name", "?")
        sandbox = pcfg.get("profile", {}).get("sandbox", "?")

        tenants.append({
            "tg_id": tg_id,
            "name": name,
            "profile": profile_name,
            "sandbox": sandbox,
        })

    return tenants


def get_subscription_info():
    """Возвращает словарь {tg_id: {tier, expires_at, active}}."""
    info = {}
    if not STARS_DB.exists():
        return info

    conn = sqlite3.connect(str(STARS_DB))
    try:
        rows = conn.execute("""
            SELECT telegram_id, telegram_username, activated_at, expires_at, active
            FROM pro_users
        """).fetchall()
        for row in rows:
            tg_id, username, activated, expires, active = row
            info[tg_id] = {
                "username": username,
                "activated": activated,
                "expires": expires,
                "active": bool(active),
            }
    except sqlite3.OperationalError:
        pass
    conn.close()
    return info


def get_rate_info():
    """Возвращает словарь {tg_id: {rpm_used, rpm_limit, rph_used, rph_limit}}."""
    info = {}
    if not RATE_DB.exists():
        return info

    conn = sqlite3.connect(str(RATE_DB))
    now = int(time.time())
    minute_start = now - (now % 60)
    hour_start = now - (now % 3600)

    try:
        rows = conn.execute("""
            SELECT 
                rc.tg_id,
                rc.tier,
                COALESCE(rc.rpm_override, 30) as rpm_limit,
                COALESCE(rc.rph_override, 500) as rph_limit,
                COALESCE((SELECT count FROM rate_limits r2 WHERE r2.tg_id=rc.tg_id AND r2.window_start=? AND r2.window_type='m'), 0) as rpm_used,
                COALESCE((SELECT count FROM rate_limits r2 WHERE r2.tg_id=rc.tg_id AND r2.window_start=? AND r2.window_type='h'), 0) as rph_used
            FROM rate_config rc
        """, (minute_start, hour_start)).fetchall()

        for row in rows:
            tg_id, tier, rpm_limit, rph_limit, rpm_used, rph_used = row
            info[tg_id] = {
                "tier": tier,
                "rpm_used": rpm_used,
                "rpm_limit": rpm_limit,
                "rpm_pct": rpm_used / rpm_limit if rpm_limit > 0 else 0,
                "rph_used": rph_used,
                "rph_limit": rph_limit,
                "rph_pct": rph_used / rph_limit if rph_limit > 0 else 0,
            }
    except sqlite3.OperationalError:
        pass
    conn.close()
    return info


def pct_class(pct):
    if pct >= 0.8:
        return "danger"
    elif pct >= 0.5:
        return "warn"
    return "ok"


def generate():
    tenants = get_tenant_list()
    subs = get_subscription_info()
    rates = get_rate_info()

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Summary
    pro_count = sum(1 for t in tenants if subs.get(t["tg_id"], {}).get("active"))
    demo_count = len(tenants) - pro_count
    total_rpm = sum(rates.get(t["tg_id"], {}).get("rpm_used", 0) for t in tenants)
    total_rph = sum(rates.get(t["tg_id"], {}).get("rph_used", 0) for t in tenants)

    summary_cards = f"""
    <div class="summary-card"><div class="number" style="color:#38bdf8">{len(tenants)}</div><div class="label">Всего тенантов</div></div>
    <div class="summary-card"><div class="number" style="color:#22c55e">{pro_count}</div><div class="label">Pro активных</div></div>
    <div class="summary-card"><div class="number" style="color:#64748b">{demo_count}</div><div class="label">Demo</div></div>
    <div class="summary-card"><div class="number" style="color:#f59e0b">{total_rpm}</div><div class="label">RPM total</div></div>
    <div class="summary-card"><div class="number" style="color:#a78bfa">{total_rph}</div><div class="label">RPH total</div></div>
    """

    # Tenant cards
    cards = []
    for t in tenants:
        tg_id = t["tg_id"]
        sub = subs.get(tg_id, {})
        rate = rates.get(tg_id, {})

        # Subscription
        if sub.get("active"):
            expires = sub.get("expires", "?")
            try:
                exp_date = datetime.strptime(expires, "%Y-%m-%d %H:%M:%S")
                days_left = (exp_date - now).days
            except (ValueError, TypeError):
                days_left = "?"
            tier_badge = '<span class="badge badge-pro">PRO</span>'
            card_class = "pro" if days_left and days_left > 0 else "expired"
            sub_text = f"Pro • {days_left}д осталось" if isinstance(days_left, int) else f"Pro • {expires[:10]}"
        else:
            tier_badge = '<span class="badge badge-demo">DEMO</span>'
            card_class = "demo"
            sub_text = "Demo • /upgrade доступен"

        # Rate
        if rate:
            rpm_pct = rate["rpm_pct"]
            rph_pct = rate["rph_pct"]
            rate_html = f"""
            <div class="metric">
                <div class="metric-label">RPM</div>
                <div class="metric-value {pct_class(rpm_pct)}">{rate['rpm_used']}/{rate['rpm_limit']} <small>({rpm_pct:.0%})</small></div>
            </div>
            <div class="metric">
                <div class="metric-label">RPH</div>
                <div class="metric-value {pct_class(rph_pct)}">{rate['rph_used']}/{rate['rph_limit']} <small>({rph_pct:.0%})</small></div>
            </div>"""
        else:
            rate_html = '<div class="metric"><div class="metric-label">Rate</div><div class="metric-value">нет данных</div></div>'

        # Vault check
        vault_exists = Path(t["sandbox"], "obsidian-vault").exists()
        vault_icon = "✅" if vault_exists else "❌"

        cards.append(f"""
        <div class="card {card_class}">
            <div class="card-header">
                <div>
                    <span class="name">@{t['name']}</span>
                    <span style="color:#64748b;font-size:13px;margin-left:8px">tg={tg_id}</span>
                </div>
                <div>{tier_badge}</div>
            </div>
            <div style="color:#94a3b8;font-size:13px;margin-bottom:10px">{sub_text} | Vault {vault_icon} | {t['profile']}</div>
            <div class="metrics">
                {rate_html}
            </div>
        </div>""")

    html = HTML_TEMPLATE.replace("{timestamp}", timestamp)
    html = html.replace("{summary_cards}", summary_cards)
    html = html.replace("{tenant_cards}", "\n".join(cards))

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html)
    print(f"✅ Дашборд сгенерирован: {DASHBOARD_PATH} ({len(tenants)} тенантов)")


if __name__ == "__main__":
    generate()
