"""Calendar accounting independent of Home Assistant's entity layer."""

from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def week_key(local: datetime) -> str:
    year, week, _ = local.isocalendar()
    return f"{year:04d}-W{week:02d}"


def period_keys(local: datetime) -> tuple[str, str, str]:
    return week_key(local), local.strftime("%Y-%m"), local.strftime("%Y")


def previous_week_key(local: datetime) -> str:
    return week_key(local - timedelta(days=7))


def adjust_time(data: dict, now: datetime, zone: ZoneInfo, seconds: float) -> None:
    """Adjust the current calendar periods and lifetime total together."""
    if not math.isfinite(seconds) or seconds == 0:
        raise ValueError("adjustment must be a finite, non-zero duration")

    keys = period_keys(now.astimezone(zone))
    changes = tuple(zip(("weeks", "months", "years"), keys))
    if data["total_seconds"] + seconds < 0 or any(
        data[bucket].get(key, 0) + seconds < 0 for bucket, key in changes
    ):
        raise ValueError("adjustment exceeds recorded downtime in the current period")

    for bucket, key in changes:
        data[bucket][key] = max(0, data[bucket].get(key, 0) + seconds)
    data["total_seconds"] = max(0, data["total_seconds"] + seconds)


def add_gap(data: dict, start: datetime, end: datetime, zone: ZoneInfo) -> bool:
    """Record a qualifying interval, assigning elapsed seconds by local day."""
    if (end - start).total_seconds() < 600:
        return False

    cursor = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    while cursor < end_utc:
        local = cursor.astimezone(zone)
        next_day = local.date() + timedelta(days=1)
        boundary = datetime.combine(next_day, time.min, zone).astimezone(timezone.utc)
        stop = min(end_utc, boundary)
        # A timezone with a skipped local midnight must still make progress.
        if stop <= cursor:
            stop = min(end_utc, cursor + timedelta(hours=1))
        seconds = (stop - cursor).total_seconds()
        for bucket, key in zip(("weeks", "months", "years"), period_keys(local)):
            data[bucket][key] = data[bucket].get(key, 0) + seconds
        cursor = stop

    data["total_seconds"] += (end_utc - start.astimezone(timezone.utc)).total_seconds()
    data["outage_count"] += 1
    data["last_gap_seconds"] = (end_utc - start.astimezone(timezone.utc)).total_seconds()
    first_week = week_key(start.astimezone(zone))
    data["week_counts"][first_week] = data["week_counts"].get(first_week, 0) + 1
    data["pending_gaps"].append([start.isoformat(), end.isoformat()])

    # Keep enough weekly history for a report after an extended absence.
    for bucket, limit in (("weeks", 54), ("months", 24), ("years", 5)):
        keys = sorted(data[bucket])
        for old in keys[:-limit]:
            del data[bucket][old]
    for old in sorted(data["week_counts"])[:-54]:
        del data["week_counts"][old]
    return True


def empty_state(now: datetime) -> dict:
    return {
        "last_seen": now.isoformat(),
        "weeks": {},
        "week_counts": {},
        "months": {},
        "years": {},
        "total_seconds": 0,
        "last_gap_seconds": None,
        "outage_count": 0,
        "pending_gaps": [],
        "last_report_week": previous_week_key(now),
    }
