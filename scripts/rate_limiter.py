#!/usr/bin/env python3
"""
Per-tenant rate limiter.
Использует SQLite для хранения счётчиков запросов.
Поддерживает два режима:
  1. rpm  — requests per minute (по умолчанию: 30 для demo, 60 для Pro)
  2. rph  — requests per hour (по умолчанию: 500 для demo, 2000 для Pro)

API:
  check(tg_id, tier='demo') -> (allowed: bool, remaining: int, reset_in: float)
  record(tg_id, tier='demo') -> None
  can_proceed(tg_id, tier='demo') -> bool  # check + record в одном вызове
"""
import os
import sqlite3
import time
from datetime import datetime

DB_PATH = os.path.expanduser("~/.hermes/data/rate_limits.db")

# Лимиты по умолчанию
TIER_LIMITS = {
    "demo": {"rpm": 30, "rph": 500},
    "pro":  {"rpm": 60, "rph": 2000},
    "admin": {"rpm": 120, "rph": 5000},
}


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            tg_id INTEGER NOT NULL,
            window_start INTEGER NOT NULL,  -- unix timestamp начала окна
            window_type TEXT NOT NULL,       -- 'm' (минута) или 'h' (час)
            count INTEGER DEFAULT 1,
            PRIMARY KEY (tg_id, window_start, window_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_config (
            tg_id INTEGER PRIMARY KEY,
            tier TEXT DEFAULT 'demo',
            rpm_override INTEGER,
            rph_override INTEGER
        )
    """)
    conn.commit()
    return conn


def _get_limits(tg_id):
    """Возвращает (rpm, rph) для пользователя с учётом overrides."""
    conn = _connect()
    row = conn.execute(
        "SELECT tier, rpm_override, rph_override FROM rate_config WHERE tg_id=?",
        (tg_id,)
    ).fetchone()
    conn.close()

    if row:
        tier, rpm_ov, rph_ov = row
    else:
        tier = "demo"
        rpm_ov = rph_ov = None

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["demo"])
    rpm = rpm_ov if rpm_ov is not None else limits["rpm"]
    rph = rph_ov if rph_ov is not None else limits["rph"]
    return rpm, rph


def check(tg_id, tier="demo"):
    """
    Проверяет, не превышен ли лимит.
    Возвращает (allowed: bool, remaining: int, reset_in: float).
    """
    now = int(time.time())
    minute_start = now - (now % 60)
    hour_start = now - (now % 3600)

    rpm_limit, rph_limit = _get_limits(tg_id)
    conn = _connect()

    # Текущие счётчики
    m_row = conn.execute(
        "SELECT count FROM rate_limits WHERE tg_id=? AND window_start=? AND window_type='m'",
        (tg_id, minute_start)
    ).fetchone()
    h_row = conn.execute(
        "SELECT count FROM rate_limits WHERE tg_id=? AND window_start=? AND window_type='h'",
        (tg_id, hour_start)
    ).fetchone()

    conn.close()

    m_count = m_row[0] if m_row else 0
    h_count = h_row[0] if h_row else 0

    m_remaining = max(0, rpm_limit - m_count)
    h_remaining = max(0, rph_limit - h_count)
    remaining = min(m_remaining, h_remaining)

    m_reset = (minute_start + 60) - now
    h_reset = (hour_start + 3600) - now
    reset_in = min(m_reset, h_reset) if remaining > 0 else max(m_reset, h_reset)

    allowed = m_count < rpm_limit and h_count < rph_limit
    return allowed, remaining, reset_in


def record(tg_id, tier="demo"):
    """Записывает использование одного запроса."""
    now = int(time.time())
    minute_start = now - (now % 60)
    hour_start = now - (now % 3600)

    conn = _connect()

    # Increment minute counter
    conn.execute("""
        INSERT INTO rate_limits (tg_id, window_start, window_type, count)
        VALUES (?, ?, 'm', 1)
        ON CONFLICT(tg_id, window_start, window_type)
        DO UPDATE SET count = count + 1
    """, (tg_id, minute_start))

    # Increment hour counter
    conn.execute("""
        INSERT INTO rate_limits (tg_id, window_start, window_type, count)
        VALUES (?, ?, 'h', 1)
        ON CONFLICT(tg_id, window_start, window_type)
        DO UPDATE SET count = count + 1
    """, (tg_id, hour_start))

    conn.commit()
    conn.close()


def can_proceed(tg_id, tier="demo"):
    """Проверяет лимит и записывает запрос если allowed. Возвращает bool."""
    allowed, _, _ = check(tg_id, tier)
    if allowed:
        record(tg_id, tier)
    return allowed


def set_tier(tg_id, tier, rpm_override=None, rph_override=None):
    """Устанавливает тариф и опциональные оверрайды для пользователя."""
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO rate_config (tg_id, tier, rpm_override, rph_override)
        VALUES (?, ?, ?, ?)
    """, (tg_id, tier, rpm_override, rph_override))
    conn.commit()
    conn.close()


def prune_old_windows():
    """Удаляет устаревшие окна (старше 2 часов)."""
    cutoff = int(time.time()) - 7200
    conn = _connect()
    conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # CLI для тестирования
    import sys
    if len(sys.argv) < 2:
        print("Usage: rate_limiter.py <tg_id> [tier]")
        sys.exit(1)
    tg_id = int(sys.argv[1])
    tier = sys.argv[2] if len(sys.argv) > 2 else "demo"
    allowed, remaining, reset_in = check(tg_id, tier)
    print(f"tg_id={tg_id} tier={tier} allowed={allowed} remaining={remaining} reset_in={reset_in}s")
    if allowed:
        record(tg_id, tier)
        print("→ записан")
