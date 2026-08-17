"""Deterministic alert policy; delivery state itself is persisted in Supabase."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


SEVERITY = {"INFO": 0, "WATCH": 1, "IMPORTANT": 2, "CRITICAL": 3}


def alert_policy(severity: str, *, minimum: str = "WATCH", now: datetime | None = None,
                 quiet_start: time = time(22, 0), quiet_end: time = time(7, 0)) -> dict:
    current = (now or datetime.now(ZoneInfo("Asia/Jakarta"))).astimezone(ZoneInfo("Asia/Jakarta"))
    level = str(severity).upper()
    if level not in SEVERITY or minimum not in SEVERITY:
        return {"send": False, "reason": "UNKNOWN_SEVERITY"}
    if SEVERITY[level] < SEVERITY[minimum]:
        return {"send": False, "reason": "BELOW_THRESHOLD"}
    local = current.time().replace(tzinfo=None)
    quiet = local >= quiet_start or local < quiet_end
    if quiet and level != "CRITICAL":
        return {"send": False, "reason": "QUIET_HOURS"}
    return {"send": True, "reason": "ELIGIBLE"}
