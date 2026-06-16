#!/usr/bin/env python3
"""
Tenant Audit Log Parser — парсит логи Hermes gateway и записывает действия тенантов.
Запускается по cron (рекомендуется раз в 5 минут).
Читает последние N строк лога, ищет сообщения от тенантов.
"""
import os
import sys
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Пути
HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
LOG_PATH = HERMES_HOME / "logs" / "gateway.log"
AUDIT_DB = HERMES_HOME / "data" / "tenant_audit.db"
STATE_FILE = HERMES_HOME / "data" / "audit_parser_state.txt"

# Паттерны для извлечения tenant-сообщений из логов Hermes
# Hermes логирует: "Processing message from user <tg_id>" или "Received message from <tg_id>"
MESSAGE_PATTERNS = [
    re.compile(r'user[_\s]?(\d{6,15})', re.IGNORECASE),
    re.compile(r'from (\d{6,15})', re.IGNORECASE),
    re.compile(r'chat[_\s]?(\d{6,15})', re.IGNORECASE),
    re.compile(r'tg[_\s]?(\d{6,15})', re.IGNORECASE),
    re.compile(r'telegram[_\s]?(\d{6,15})', re.IGNORECASE),
]

# Игнорируем админские ID
ADMIN_IDS = {5529208670, 319665243}


def get_last_position():
    """Читает последнюю обработанную позицию в логе."""
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except ValueError:
            pass
    return 0


def save_position(pos):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(pos))


def extract_tg_id(line):
    """Пытается извлечь tg_id из строки лога."""
    for pattern in MESSAGE_PATTERNS:
        match = pattern.search(line)
        if match:
            tg_id = int(match.group(1))
            if tg_id not in ADMIN_IDS:
                return tg_id
    return None


def log_action(tg_id, action, details=""):
    """Записать действие в аудит-лог."""
    os.makedirs(os.path.dirname(AUDIT_DB), exist_ok=True)
    conn = sqlite3.connect(str(AUDIT_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tg_id ON audit_log(tg_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
    conn.execute(
        "INSERT INTO audit_log (tg_id, action, details) VALUES (?,?,?)",
        (tg_id, action, details[:500])
    )
    conn.commit()
    conn.close()


def main():
    if not LOG_PATH.exists():
        print(f"Лог не найден: {LOG_PATH}")
        return

    last_pos = get_last_position()
    file_size = LOG_PATH.stat().st_size

    if file_size <= last_pos:
        return  # нет новых данных

    with open(LOG_PATH) as f:
        f.seek(last_pos)
        new_lines = f.readlines()

    new_actions = 0
    for line in new_lines:
        tg_id = extract_tg_id(line)
        if tg_id:
            # Определяем тип действия
            if 'error' in line.lower() or 'fail' in line.lower():
                action = "error"
            elif 'start' in line.lower():
                action = "start"
            elif 'command' in line.lower():
                action = "command"
            else:
                action = "message"

            details = line.strip()[:200]
            log_action(tg_id, action, details)
            new_actions += 1

    save_position(file_size)

    if new_actions > 0:
        print(f"[AUDIT-PARSER] {datetime.now().strftime('%H:%M')} — {new_actions} новых действий")
    # Тихо если ничего нового


if __name__ == "__main__":
    main()
