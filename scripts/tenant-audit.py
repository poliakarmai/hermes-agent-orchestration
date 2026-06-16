#!/usr/bin/env python3
"""
Tenant Audit Trail — логирование и просмотр действий тенантов.
Хранит: tg_id, action, details, timestamp в SQLite.

API:
  audit_logger.log_action(tg_id, action, details="") -> None
  audit_logger.query(tg_id=None, action=None, limit=50) -> list[dict]
  audit_logger.generate_report(days=7) -> str

CLI: tenant-audit.py <tg_id> [days]
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.hermes/data/tenant_audit.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    return conn


def log_action(tg_id, action, details=""):
    """Записать действие тенанта в аудит-лог."""
    conn = _connect()
    conn.execute(
        "INSERT INTO audit_log (tg_id, action, details) VALUES (?,?,?)",
        (tg_id, action, details[:500])
    )
    conn.commit()
    conn.close()


def query(tg_id=None, action=None, days=7, limit=100):
    """Запросить логи. Возвращает список словарей."""
    conn = _connect()
    where = ["created_at > datetime('now','localtime', ?)"]
    params = [f"-{days} days"]

    if tg_id:
        where.append("tg_id = ?")
        params.append(tg_id)
    if action:
        where.append("action = ?")
        params.append(action)

    sql = f"SELECT id, tg_id, action, details, created_at FROM audit_log WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [
        {"id": r[0], "tg_id": r[1], "action": r[2], "details": r[3], "created_at": r[4]}
        for r in rows
    ]


def get_stats(days=7):
    """Статистика по тенантам за период."""
    conn = _connect()
    rows = conn.execute("""
        SELECT tg_id, 
               COUNT(*) as total_actions,
               COUNT(DISTINCT action) as unique_actions,
               MAX(created_at) as last_active
        FROM audit_log 
        WHERE created_at > datetime('now','localtime', ?)
        GROUP BY tg_id
        ORDER BY total_actions DESC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [
        {"tg_id": r[0], "total": r[1], "unique": r[2], "last_active": r[3]}
        for r in rows
    ]


def generate_report(days=7):
    """Генерирует текстовый отчёт."""
    stats = get_stats(days)
    if not stats:
        return f"Нет данных за {days} дн."

    lines = [f"📊 *Аудит-трейл за {days} дн.*\n"]
    lines.append(f"Всего тенантов активно: {len(stats)}\n")

    for s in stats:
        lines.append(
            f"• `{s['tg_id']}`: {s['total']} действий, "
            f"последняя активность: {s['last_active'][:16] if s['last_active'] else '?'}"
        )

    return "\n".join(lines)


def prune_old(days=90):
    """Удаляет записи старше N дней."""
    conn = _connect()
    conn.execute(
        "DELETE FROM audit_log WHERE created_at < datetime('now','localtime', ?)",
        (f"-{days} days",)
    )
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    return deleted


def main():
    if len(sys.argv) < 2:
        print("Usage: tenant-audit.py <tg_id|all|stats|prune> [days]")
        print("  tenant-audit.py 5529208670        — логи конкретного тенанта за 7 дн")
        print("  tenant-audit.py all 30            — все логи за 30 дн")
        print("  tenant-audit.py stats             — статистика за 7 дн")
        print("  tenant-audit.py prune 90          — удалить старее 90 дн")
        sys.exit(1)

    cmd = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    if cmd == "stats":
        print(generate_report(days))
    elif cmd == "prune":
        deleted = prune_old(days)
        print(f"🗑️ Удалено {deleted} записей старше {days} дн.")
    elif cmd == "all":
        rows = query(days=days, limit=200)
        for r in rows:
            print(f"[{r['created_at'][:16]}] tg={r['tg_id']} | {r['action']} | {r['details'][:80]}")
        print(f"\n— {len(rows)} записей")
    else:
        try:
            tg_id = int(cmd)
        except ValueError:
            print(f"❌ Неверный tg_id: {cmd}")
            sys.exit(1)
        rows = query(tg_id=tg_id, days=days, limit=100)
        for r in rows:
            print(f"[{r['created_at'][:16]}] {r['action']} | {r['details'][:80]}")
        print(f"\n— {len(rows)} записей")


if __name__ == "__main__":
    main()
