#!/usr/bin/env python3
"""
Tenant Metrics Collector — собирает метрики по тенантам и сохраняет в SQLite.
Источники: логи Hermes gateway, apolaibot-demo, rate_limits, audit_log.
Запускается по cron (рекомендуется раз в 5 минут).
"""
import os
import sys
import re
import sqlite3
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
METRICS_DB = HERMES_HOME / "data" / "tenant_metrics.db"
AUDIT_DB = HERMES_HOME / "data" / "tenant_audit.db"
RATE_DB = HERMES_HOME / "data" / "rate_limits.db"
LOG_PATH = HERMES_HOME / "logs" / "gateway.log"
STATE_FILE = HERMES_HOME / "data" / "metrics_state.json"

# Паттерны для latency (Hermes логирует время ответа)
LATENCY_PATTERNS = [
    re.compile(r'completed in (\d+\.?\d*)s', re.IGNORECASE),
    re.compile(r'response time[:\s]+(\d+\.?\d*)s?', re.IGNORECASE),
    re.compile(r'latency[:\s]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'duration[:\s]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)s \(api', re.IGNORECASE),
]


def _connect():
    os.makedirs(METRICS_DB.parent, exist_ok=True)
    conn = sqlite3.connect(str(METRICS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics_hourly (
            tg_id INTEGER NOT NULL,
            hour TEXT NOT NULL,  -- 'YYYY-MM-DD HH:00'
            requests INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            total_latency REAL DEFAULT 0.0,  -- суммарная latency в секундах
            latency_samples INTEGER DEFAULT 0,
            PRIMARY KEY (tg_id, hour)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_hour ON metrics_hourly(hour)")
    return conn


def get_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"log_position": 0, "last_hour_processed": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def extract_tg_id(line):
    """Извлекает tg_id из строки лога."""
    for pattern in [
        re.compile(r'user[_\s]?(\d{6,15})', re.IGNORECASE),
        re.compile(r'from (\d{6,15})', re.IGNORECASE),
        re.compile(r'chat[_\s]?(\d{6,15})', re.IGNORECASE),
    ]:
        m = pattern.search(line)
        if m:
            tid = int(m.group(1))
            if tid not in {5529208670, 319665243}:  # не админы
                return tid
    return None


def extract_latency(line):
    for pattern in LATENCY_PATTERNS:
        m = pattern.search(line)
        if m:
            return float(m.group(1))
    return None


def parse_logs():
    """Парсит новые строки лога и возвращает метрики."""
    if not LOG_PATH.exists():
        return defaultdict(lambda: {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})

    state = get_state()
    file_size = LOG_PATH.stat().st_size

    if file_size <= state["log_position"]:
        return defaultdict(lambda: {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})

    with open(LOG_PATH) as f:
        f.seek(state["log_position"])
        lines = f.readlines()

    state["log_position"] = file_size
    metrics = defaultdict(lambda: {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})

    for line in lines:
        tg_id = extract_tg_id(line)
        if not tg_id:
            continue

        is_error = any(w in line.lower() for w in ['error', 'fail', 'timeout', 'exception', 'traceback'])
        latency = extract_latency(line)

        metrics[tg_id]["requests"] += 1
        if is_error:
            metrics[tg_id]["errors"] += 1
        if latency is not None and latency < 300:  # фильтруем аномальные значения
            metrics[tg_id]["latency_sum"] += latency
            metrics[tg_id]["latency_n"] += 1

    save_state(state)
    return metrics


def get_audit_metrics():
    """Собирает метрики из аудит-лога."""
    if not AUDIT_DB.exists():
        return defaultdict(lambda: {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})

    conn = sqlite3.connect(str(AUDIT_DB))
    this_hour = datetime.now().strftime("%Y-%m-%d %H:00")

    rows = conn.execute("""
        SELECT tg_id, action, COUNT(*) as cnt
        FROM audit_log
        WHERE created_at >= datetime('now','localtime','-1 hour')
        GROUP BY tg_id, action
    """).fetchall()
    conn.close()

    metrics = defaultdict(lambda: {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})
    for tg_id, action, cnt in rows:
        if action == "error":
            metrics[tg_id]["errors"] += cnt
        else:
            metrics[tg_id]["requests"] += cnt

    return metrics


def collect():
    """Собирает все метрики и сохраняет в БД."""
    now = datetime.now()
    hour_key = now.strftime("%Y-%m-%d %H:00")

    # Метрики из логов
    log_metrics = parse_logs()
    # Метрики из аудит-лога
    audit_metrics = get_audit_metrics()

    # Объединяем
    all_tg_ids = set(log_metrics.keys()) | set(audit_metrics.keys())

    if not all_tg_ids:
        return

    conn = _connect()
    inserted = 0
    for tg_id in all_tg_ids:
        lm = log_metrics.get(tg_id, {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})
        am = audit_metrics.get(tg_id, {"requests": 0, "errors": 0, "latency_sum": 0, "latency_n": 0})

        total_req = lm["requests"] + am["requests"]
        total_err = lm["errors"] + am["errors"]
        total_lat = lm["latency_sum"] + am["latency_sum"]
        total_lat_n = lm["latency_n"] + am["latency_n"]

        if total_req == 0:
            continue

        conn.execute("""
            INSERT INTO metrics_hourly (tg_id, hour, requests, errors, total_latency, latency_samples)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tg_id, hour) DO UPDATE SET
                requests = requests + excluded.requests,
                errors = errors + excluded.errors,
                total_latency = total_latency + excluded.total_latency,
                latency_samples = latency_samples + excluded.latency_samples
        """, (tg_id, hour_key, total_req, total_err, total_lat, total_lat_n))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"[METRICS] {now.strftime('%H:%M')} — {inserted} тенантов, {sum(m['requests'] for m in log_metrics.values())} запросов из логов")


def get_summary(hours=24):
    """Возвращает сводку метрик за последние N часов."""
    if not METRICS_DB.exists():
        return {}

    conn = sqlite3.connect(str(METRICS_DB))
    rows = conn.execute("""
        SELECT tg_id,
               SUM(requests) as total_req,
               SUM(errors) as total_err,
               SUM(total_latency) as total_lat,
               SUM(latency_samples) as lat_n
        FROM metrics_hourly
        WHERE hour >= datetime('now','localtime', ?)
        GROUP BY tg_id
        ORDER BY total_req DESC
    """, (f"-{hours} hours",)).fetchall()
    conn.close()

    result = {}
    for tg_id, req, err, lat, lat_n in rows:
        avg_lat = (lat / lat_n * 1000) if lat_n and lat_n > 0 else 0  # в мс
        err_rate = (err / req * 100) if req > 0 else 0
        result[tg_id] = {
            "requests": req,
            "errors": err,
            "error_rate": round(err_rate, 1),
            "avg_latency_ms": round(avg_lat, 0),
        }
    return result


def prune_old(days=30):
    if not METRICS_DB.exists():
        return 0
    conn = sqlite3.connect(str(METRICS_DB))
    conn.execute(
        "DELETE FROM metrics_hourly WHERE hour < datetime('now','localtime', ?)",
        (f"-{days} days",)
    )
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    return deleted


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        summary = get_summary()
        print(json.dumps(summary, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "prune":
        deleted = prune_old()
        print(f"🗑️ Metrics pruned: {deleted} rows")
    else:
        collect()
