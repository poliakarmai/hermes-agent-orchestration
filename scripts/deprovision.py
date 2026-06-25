#!/usr/bin/env python3
"""
Депровижнинг: отключение Pro-подписки при истечении срока.
Запускается по cron (рекомендуется раз в 30 минут).
"""
import os
import sqlite3
import subprocess
import sys
import json
from datetime import datetime
from urllib.request import urlopen, Request

DB_PATH = os.path.expanduser("~/.hermes/data/stars_payments.db")
ENV_PATH = os.path.expanduser("~/.hermes/.env")
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hermes_config import ADMIN_IDS
ADMIN_ID = next(iter(ADMIN_IDS))


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


def tg_send(chat_id, text, bot_token):
    """Отправляет сообщение через Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def offboard_tenant(tg_id):
    """Вызывает hermes-tenant offboard."""
    result = subprocess.run(
        ["hermes-tenant", "offboard", "--tg-id", str(tg_id)],
        capture_output=True, text=True, timeout=60
    )
    print(f"  offboard exit={result.returncode}")
    if result.stdout:
        print(f"  stdout: {result.stdout.strip()}")
    if result.stderr:
        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def main():
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не найден в .env", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print("ℹ️ БД не найдена, нечего депровижнить")
        return

    conn = sqlite3.connect(DB_PATH)
    expired = conn.execute("""
        SELECT telegram_id, telegram_username, activated_at, expires_at
        FROM pro_users
        WHERE active = 1 AND expires_at < datetime('now','localtime')
    """).fetchall()

    if not expired:
        conn.close()
        return

    for tg_id, username, activated, expires in expired:
        print(f"[DEPROVISION] @{username} ({tg_id}) — истекла {expires}")

        success = offboard_tenant(tg_id)

        if success:
            conn.execute(
                "UPDATE pro_users SET active = 0 WHERE telegram_id = ?",
                (tg_id,)
            )

            # Уведомление пользователю
            try:
                tg_send(tg_id, (
                    "⚠️ *Подписка Pro истекла.*\n\n"
                    "Доступ к @Morearbot приостановлен.\n"
                    "Продлить: @miropolbot → /start → 100 ⭐\n\n"
                    "Бесплатный бот по-прежнему доступен в @Apolaibot 🤖"
                ), bot_token)
                print(f"  ✅ Уведомление пользователю отправлено")
            except Exception as e:
                print(f"  ⚠️ Не удалось уведомить пользователя: {e}")

            # Уведомление админу
            try:
                tg_send(ADMIN_ID, (
                    f"🚫 *Клиент отключён — подписка истекла*\n\n"
                    f"Пользователь: @{username}\n"
                    f"ID: `{tg_id}`\n"
                    f"Подписка истекла: {expires}\n"
                    f"Статус: депровижнинг ✅"
                ), bot_token)
                print(f"  ✅ Уведомление админу отправлено")
            except Exception as e:
                print(f"  ⚠️ Не удалось уведомить админа: {e}")
        else:
            print(f"  ❌ Ошибка депровижнинга — offboard вернул ошибку")

    conn.commit()
    conn.close()

    # Если были изменения — рестартуем gateway
    if expired:
        os.system("systemctl --user restart hermes-gateway 2>&1")
        print("[DEPROVISION] Gateway restarted")


if __name__ == "__main__":
    main()
