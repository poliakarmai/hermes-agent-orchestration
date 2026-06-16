#!/usr/bin/env python3
"""
Активатор Pro-подписки — проверяет БД платежей, создаёт tenant'ов через hermes-tenant onboard.
Запускается по cron раз в 2 минуты.
"""

import os
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from urllib.request import urlopen, Request

ENV_PATH = os.path.expanduser("~/.hermes/.env")
ADMIN_ID = 5529208670  # Поляков Алексей


def load_env():
    """Загружает переменные из .env файла."""
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def notify_admin(username, tg_id, bot_token):
    """Уведомление админа о новом Pro-клиенте."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": ADMIN_ID,
            "text": (
                f"🎉 *Новый клиент Pro!*\n\n"
                f"Пользователь: @{username}\n"
                f"ID: `{tg_id}`\n"
                f"Тариф: Pro (30 дн)\n"
                f"Стоимость: 100 ⭐\n"
                f"Статус: активирован ✅"
            ),
            "parse_mode": "Markdown"
        }).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[NOTIFY] Ошибка уведомления админа: {e}", file=sys.stderr)
        return None

DB_PATH = os.path.expanduser("~/.hermes/data/stars_payments.db")


def onboard_tenant(tg_id, username):
    """Вызывает hermes-tenant onboard для создания полноценного профиля."""
    name = username.replace("@", "") if username else f"user{tg_id}"
    result = subprocess.run(
        ["hermes-tenant", "onboard", "--tg-id", str(tg_id), "--name", name],
        capture_output=True, text=True, timeout=60
    )
    print(f"[ONBOARD] {username} ({tg_id}): {'✅' if result.returncode == 0 else '❌'}")
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode == 0


def main():
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)

    # Найти подтверждённые платежи с неактивированным статусом
    rows = conn.execute("""
        SELECT p.telegram_id, p.telegram_username, p.amount_stars, p.telegram_payment_id
        FROM payments p
        LEFT JOIN pro_users pu ON p.telegram_id = pu.telegram_id
        WHERE p.status = 'confirmed' AND pu.telegram_id IS NULL
    """).fetchall()

    if not rows:
        conn.close()
        return

    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")

    activated_users = []

    for row in rows:
        tg_id, username, amount, payment_id = row

        # Авто-онбординг: создаём Linux-пользователя, профиль, .env
        success = onboard_tenant(tg_id, username)

        status = "activated" if success else "failed"
        conn.execute(
            f"UPDATE payments SET status=?, activated_at=datetime('now','localtime') WHERE telegram_payment_id=?",
            (status, payment_id)
        )
        conn.execute(
            "INSERT OR REPLACE INTO pro_users (telegram_id, telegram_username, activated_at, expires_at, active) VALUES (?,?,datetime('now','localtime'),datetime('now','+30 days'),?)",
            (tg_id, username, 1 if success else 0)
        )

        if success:
            activated_users.append((tg_id, username))

    conn.commit()
    conn.close()

    if activated_users:
        # Уведомление админа о каждом новом клиенте
        if bot_token:
            for tg_id, username in activated_users:
                notify_admin(username, tg_id, bot_token)

        # Перезагружаем gateway чтобы подхватил channel_profiles
        os.system("systemctl --user restart hermes-gateway 2>&1")
        print("[ACTIVATE] Gateway restarted")


if __name__ == "__main__":
    main()
