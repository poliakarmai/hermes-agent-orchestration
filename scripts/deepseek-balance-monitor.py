#!/usr/bin/env python3
"""
DeepSeek Balance Monitor — проверяет работоспособность API и оценивает расходы.
Запускается по cron (рекомендуется раз в час).
Алертит админа при ошибках биллинга или превышении порога расходов.
"""
import os
import sys
import json
import sqlite3
import time
from datetime import datetime
from urllib.request import urlopen, Request

ENV_PATH = os.path.expanduser("~/.hermes/.env")
RATE_DB = os.path.expanduser("~/.hermes/data/rate_limits.db")
ADMIN_ID = 5529208670

# Пороги алертов
MONTHLY_SPEND_LIMIT_USD = 50.0   # алерт при превышении
DEEPSEEK_PRICE_PER_1M = 0.27     # $0.27 за 1M токенов (deepseek-chat)

BALANCE_CHECK_URL = "https://api.deepseek.com/v1/models"


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


def check_api_health(api_key):
    """Проверяет, жив ли API ключ. Возвращает (ok, error_msg)."""
    try:
        req = Request(
            BALANCE_CHECK_URL,
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return True, None
            elif resp.status == 402:
                return False, "PAYMENT_REQUIRED: баланс DeepSeek исчерпан или требуется пополнение"
            elif resp.status == 401:
                return False, "UNAUTHORIZED: API ключ недействителен"
            else:
                return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, f"Connection error: {e}"


def get_monthly_token_usage():
    """Считает общее потребление токенов за текущий месяц."""
    if not os.path.exists(RATE_DB):
        return 0

    month_key = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(RATE_DB)
    try:
        row = conn.execute(
            "SELECT SUM(tokens_used) FROM token_budget WHERE month_key=?",
            (month_key,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = [0]
    conn.close()

    return row[0] if row[0] else 0


def estimate_cost(total_tokens):
    """Оценивает стоимость в USD."""
    return (total_tokens / 1_000_000) * DEEPSEEK_PRICE_PER_1M


def alert_admin(bot_token, message):
    """Шлёт алерт админу через Telegram."""
    if not bot_token:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": ADMIN_ID,
            "text": message,
            "parse_mode": "Markdown"
        }).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"[ALERT] Failed: {e}", file=sys.stderr)
        return False


def main():
    env = load_env()
    api_key = env.get("DEEPSEEK_API_KEY", "")
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")

    now = datetime.now().strftime("%H:%M")

    # 1. Health check
    if api_key:
        ok, error = check_api_health(api_key)
        if not ok:
            msg = f"🔴 *DeepSeek API Alert!*\n\n{error}\n\nПроверено: {now}"
            print(f"[BALANCE] ❌ {error}")
            alert_admin(bot_token, msg)
            sys.exit(1)
        else:
            print(f"[BALANCE] {now} — API OK")
    else:
        print(f"[BALANCE] {now} — no DEEPSEEK_API_KEY, skipping health check")

    # 2. Token usage / cost estimate
    total_tokens = get_monthly_token_usage()
    cost = estimate_cost(total_tokens)

    if total_tokens > 0:
        print(f"[BALANCE] {now} — {total_tokens:,} токенов/мес (~${cost:.2f})")

    if cost > MONTHLY_SPEND_LIMIT_USD:
        msg = (
            f"⚠️ *DeepSeek — порог расходов!*\n\n"
            f"Потрачено за месяц: ~${cost:.2f}\n"
            f"Токенов: {total_tokens:,}\n"
            f"Лимит алерта: ${MONTHLY_SPEND_LIMIT_USD}\n\n"
            f"Проверено: {now}"
        )
        alert_admin(bot_token, msg)
        print(f"[BALANCE] ⚠️ Exceeded ${MONTHLY_SPEND_LIMIT_USD} limit!")


if __name__ == "__main__":
    main()
