"""Time verification. GitHub cron can be late; skip the run if it started too late.

Usage in a workflow:  python -m shorts.timeguard --slot 10am
Writes run=true|false, message, target_iso to $GITHUB_OUTPUT.
Manual (workflow_dispatch) runs always pass.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import EARLY_TOLERANCE_MINUTES, LEAD_MINUTES, MAX_DELAY_MINUTES, SLOTS, TZ


@dataclass
class Guard:
    run: bool
    target: datetime          # local publish target (aware)
    expected_start: datetime  # target - lead (aware, UTC)
    late_minutes: float
    message: str


def evaluate(slot: str, now: datetime | None = None, tz: str = TZ,
             lead: int = LEAD_MINUTES, max_delay: int = MAX_DELAY_MINUTES) -> Guard:
    now = now or datetime.now(timezone.utc)
    z = ZoneInfo(tz)
    hour, minute = SLOTS[slot]
    local_now = now.astimezone(z)
    best = None
    for day_shift in (-1, 0, 1):  # the nearest occurrence of this slot, even across midnight
        d = (local_now + timedelta(days=day_shift)).date()
        target = datetime(d.year, d.month, d.day, hour, minute, tzinfo=z)
        start = target.astimezone(timezone.utc) - timedelta(minutes=lead)
        late = (now - start).total_seconds() / 60.0
        if best is None or abs(late) < abs(best[2]):
            best = (target, start, late)
    target, start, late = best
    if late > max_delay:
        return Guard(False, target, start, late,
                     f"DELAYED SKIP: slot {slot} started {late:.0f} min late "
                     f"(limit {max_delay} min). Skipping this run.")
    if late < -EARLY_TOLERANCE_MINUTES:
        return Guard(False, target, start, late,
                     f"TOO EARLY: slot {slot} started {-late:.0f} min before its expected time. Skipping.")
    return Guard(True, target, start, late,
                 f"OK: slot {slot} started {late:+.0f} min from expected; publish target {target:%H:%M} {tz}.")


def _gh_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS))
    a = ap.parse_args()
    g = evaluate(a.slot)
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    run = g.run or manual
    msg = g.message + (" (manual run: guard bypassed)" if manual and not g.run else "")
    print(msg)
    _gh_output("run", "true" if run else "false")
    _gh_output("message", msg)
    _gh_output("target_iso", "" if manual else g.target.isoformat())


if __name__ == "__main__":
    main()
