#!/usr/bin/env python3
"""
Tenant Rate Watchdog — мониторинг использования rate limits тенантами.
Запускается по cron (рекомендуется раз в 10-15 минут).
При превышении 80% лимита — алерт админу.
"""
import os
import sys
import json
import sqlite3
import time
from datetime import datetime
from urllib.request import urlopen, Request

DB_PATH = os.path.expanduser("~/.hermes/data/rate_limits.db")
ENV_PATH = os.path.expanduser("~/.hermes/.env")
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hermes_config import ADMIN_IDS
ADMIN_ID = next(iter(ADMIN_IDS))
ALERT_THRESHOLD = 0.8  # алерт при 80% использования


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def get_usage():
    """Возвращает словарь {tg_id: {tier, rpm_used, rpm_limit, rph_used, rph_limit}}."""
    if not os.path.exists(DB_PATH):
        return {}

    conn = sqlite3.connect(DB_PATH)
    now = int(time.time())
    minute_start = now - (now % 60)
    hour_start = now - (now % 3600)

    # Текущие счётчики за минуту и час
    rows = conn.execute("""
        SELECT 
            rl.tg_id,
            rc.tier,
            COALESCE(rc.rpm_override, CASE WHEN rc.tier='pro' THEN 60 WHEN rc.tier='admin' THEN 120 ELSE 30 END) as rpm_limit,
            COALESCE(rc.rph_override, CASE WHEN rc.tier='pro' THEN 2000 WHEN rc.tier='admin' THEN 5000 ELSE 500 END) as rph_limit,
            COALESCE((SELECT count FROM rate_limits r2 WHERE r2.tg_id=rl.tg_id AND r2.window_start=? AND r2.window_type='m'), 0) as rpm_used,
            COALESCE((SELECT count FROM rate_limits r2 WHERE r2.tg_id=rl.tg_id AND r2.window_start=? AND r2.window_type='h'), 0) as rph_used
        FROM rate_limits rl
        LEFT JOIN rate_config rc ON rl.tg_id = rc.tg_id
        WHERE rl.window_start >= ? 
        GROUP BY rl.tg_id
    """, (minute_start, hour_start, hour_start)).fetchall()

    conn.close()

    usage = {}
    for row in rows:
        tg_id, tier, rpm_limit, rph_limit, rpm_used, rph_used = row
        usage[tg_id] = {
            "tier": tier or "demo",
            "rpm_used": rpm_used,
            "rpm_limit": rpm_limit,
            "rpm_pct": rpm_used / rpm_limit if rpm_limit > 0 else 0,
            "rph_used": rph_used,
            "rph_limit": rph_limit,
            "rph_pct": rph_used / rph_limit if rph_limit > 0 else 0,
        }
    return usage


def alert_admin(high_usage, bot_token):
    """Шлёт алерт админу о тенантах, приближающихся к лимиту."""
    if not bot_token or not high_usage:
        return

    lines = []
    for tg_id, u in sorted(high_usage.items(), key=lambda x: max(x[1]["rpm_pct"], x[1]["rph_pct"]), reverse=True):
        tier = u["tier"]
        r_icon = "🔴" if u["rpm_pct"] >= 1.0 else "🟡"
        h_icon = "🔴" if u["rph_pct"] >= 1.0 else "🟡"
        lines.append(
            f"{r_icon} `{tg_id}` ({tier}): "
            f"RPM {u['rpm_used']}/{u['rpm_limit']} ({u['rpm_pct']:.0%}) | "
            f"RPH {u['rph_used']}/{u['rph_limit']} ({u['rph_pct']:.0%})"
        )

    text = "⚠️ *Rate limit alert* — тенанты >80% лимита:\n\n" + "\n".join(lines)

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": ADMIN_ID,
            "text": text,
            "parse_mode": "Markdown"
        }).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30):
            pass
    except Exception as e:
        print(f"[ALERT] Failed to send: {e}", file=sys.stderr)


def main():
    usage = get_usage()
    if not usage:
        return

    # Фильтруем тенантов с >80% использования
    high_usage = {
        tg_id: u for tg_id, u in usage.items()
        if u["rpm_pct"] >= ALERT_THRESHOLD or u["rph_pct"] >= ALERT_THRESHOLD
    }

    if high_usage:
        print(f"[RATE-WATCH] {datetime.now().strftime('%H:%M')} — {len(high_usage)} tenants near limit:")
        for tg_id, u in sorted(high_usage.items(), key=lambda x: max(x[1]["rpm_pct"], x[1]["rph_pct"]), reverse=True):
            print(f"  tg={tg_id} tier={u['tier']} rpm={u['rpm_used']}/{u['rpm_limit']} rph={u['rph_used']}/{u['rph_limit']}")

        env = load_env()
        bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
        if bot_token:
            alert_admin(high_usage, bot_token)
    else:
        # Тихо — все в пределах нормы
        total = len(usage)
        if total > 0:
            max_rpm = max(u["rpm_pct"] for u in usage.values())
            max_rph = max(u["rph_pct"] for u in usage.values())
            print(f"[RATE-WATCH] {datetime.now().strftime('%H:%M')} — {total} tenants OK (max rpm={max_rpm:.0%} rph={max_rph:.0%})")


if __name__ == "__main__":
    main()
