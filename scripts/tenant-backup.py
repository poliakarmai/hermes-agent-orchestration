#!/usr/bin/env python3
"""
Auto-backup tenant profiles — ежедневный бэкап всех профилей тенантов.
Ротирует: хранит 7 последних бэкапов.
"""
import os
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from glob import glob

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
BACKUP_DIR = HERMES_HOME / "backups" / "daily"
PROFILES_DIR = HERMES_HOME / "profiles"
CONFIG_YAML = HERMES_HOME / "config.yaml"
STARS_DB = HERMES_HOME / "data" / "stars_payments.db"
KEEP_DAYS = 7


def rotate_backups():
    """Удаляет бэкапы старше KEEP_DAYS."""
    pattern = str(BACKUP_DIR / "tenant-backup-*.tar.gz")
    files = sorted(glob(pattern))
    cutoff = time.time() - (KEEP_DAYS * 86400)

    deleted = 0
    for f in files:
        if os.path.getmtime(f) < cutoff:
            os.remove(f)
            deleted += 1

    if deleted:
        print(f"  🗑️ Ротация: удалено {deleted} старых бэкапов")


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_path = BACKUP_DIR / f"tenant-backup-{timestamp}.tar.gz"

    print(f"[BACKUP] {datetime.now().strftime('%H:%M')} — создаю {backup_path.name}")

    with tarfile.open(backup_path, "w:gz") as tar:
        # Все профили тенантов
        if PROFILES_DIR.exists():
            for profile_dir in PROFILES_DIR.iterdir():
                if profile_dir.is_dir():
                    tar.add(str(profile_dir), arcname=f"profiles/{profile_dir.name}")

        # Основной конфиг
        if CONFIG_YAML.exists():
            tar.add(str(CONFIG_YAML), arcname="config.yaml")

        # База платежей
        if STARS_DB.exists():
            tar.add(str(STARS_DB), arcname="data/stars_payments.db")

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ Бэкап: {backup_path} ({size_mb:.1f} MB)")

    # Ротация
    rotate_backups()

    # Список активных бэкапов
    remaining = sorted(glob(str(BACKUP_DIR / "tenant-backup-*.tar.gz")))
    print(f"  📦 Бэкапов хранится: {len(remaining)} (из макс {KEEP_DAYS})")


if __name__ == "__main__":
    backup()
