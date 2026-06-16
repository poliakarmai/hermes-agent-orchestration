#!/usr/bin/env python3
"""
Активатор Pro-подписки — проверяет БД платежей, создаёт tenant'ов через hermes-tenant onboard.
Запускается по cron раз в 2 минуты.
"""

import os
import sqlite3
import subprocess
import sys
from datetime import datetime

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

    conn.commit()
    conn.close()

    if any(r for r in rows if True):  # если были активации
        # Перезагружаем gateway чтобы подхватил channel_profiles
        os.system("systemctl --user restart hermes-gateway 2>&1")
        print("[ACTIVATE] Gateway restarted")


if __name__ == "__main__":
    main()
