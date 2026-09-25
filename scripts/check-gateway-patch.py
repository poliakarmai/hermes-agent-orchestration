#!/usr/bin/env python3
"""Watchdog: проверяет наличие gateway-патча disabled_toolsets после обновлений Hermes.

Запускается cron-джобой каждые 10 минут (no_agent=true).
При отсутствии патча — пытается переприменить, пишет алерт при неудаче.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

RUN_PY = Path.home() / ".local" / "lib" / "python3.12" / "site-packages" / "gateway" / "run.py"
PATCH_FILE = Path.home() / ".hermes" / "patches" / "gateway-disabled-toolsets.py"
ALERT_LOG = Path.home() / ".hermes" / "logs" / "gateway-patch.log"
MARKER = "MCP isolation: tenants must not inherit"
ANCHOR = "        disabled_toolsets = agent_cfg_local.get(\"disabled_toolsets\") or None"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def check_patch() -> bool:
    """True если патч на месте."""
    if not RUN_PY.exists():
        log(f"SKIP: {RUN_PY} не существует")
        return True  # не алертить — репо не клонирован

    content = RUN_PY.read_text()
    if MARKER in content:
        return True
    return False


def apply_patch() -> bool:
    """Вставить патч после ANCHOR. Возвращает True если успешно."""
    if not PATCH_FILE.exists():
        log(f"FAIL: патч-файл {PATCH_FILE} не найден")
        return False

    content = RUN_PY.read_text()
    if ANCHOR not in content:
        log(f"FAIL: якорь '{ANCHOR[:50]}...' не найден — структура изменилась")
        return False

    patch_code = PATCH_FILE.read_text().rstrip("\n")
    insertion = f"{ANCHOR}\n{patch_code}"
    old_block = ANCHOR

    new_content = content.replace(old_block, insertion, 1)
    if new_content == content:
        log("FAIL: не удалось вставить патч (replace не сработал)")
        return False

    RUN_PY.write_text(new_content)
    log("OK: патч переприменён автоматически")
    return True


def main():
    if check_patch():
        # Всё ок, silent
        return 0

    log("ALERT: патч disabled_toolsets отсутствует! Пытаюсь переприменить...")

    if apply_patch():
        return 0

    log("CRITICAL: не удалось переприменить патч — требуется ручное вмешательство!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
