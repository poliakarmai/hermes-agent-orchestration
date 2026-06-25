"""
Shared Hermes config — reads ADMIN_IDS and UNLIMITED_USERS from env vars.
Import this instead of hardcoding IDs in individual scripts.

Env vars:
  HERMES_ADMIN_IDS=5529208670,319665243
  HERMES_UNLIMITED_USERS=319665243,2115597720,470549555
"""
import os

def _parse_ids(env_var: str, default: str) -> set[int]:
    raw = os.environ.get(env_var, default)
    return {int(x.strip()) for x in raw.split(",") if x.strip()}

ADMIN_IDS = _parse_ids("HERMES_ADMIN_IDS", "5529208670,319665243")
UNLIMITED_USERS = _parse_ids("HERMES_UNLIMITED_USERS", "319665243,2115597720,470549555")
