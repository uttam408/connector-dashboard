#!/usr/bin/env python3
"""
schedule.py -- turn a recurrence spec into the concrete next run, e.g.
"tonight 11 PM", "tomorrow 6 AM", "Thu 11 PM".

Spec grammar:  "<DAYS> <TIMES>"
  DAYS  = DAILY  |  comma list of MON TUE WED THU FRI SAT SUN
  TIMES = comma list of HH:MM (24h)

  "DAILY 06:00"                 every day at 6am
  "DAILY 06:00,07:00,08:00"     every day, three times
  "MON,THU 23:00"               Mondays and Thursdays at 11pm

Shared by report.py (agents declare their schedule; the concrete instance is
recomputed every time they report) and check.py (same, for the agents it
still backstops).
"""

from datetime import datetime, timedelta

_WD = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def _ampm(h, m):
    label = f"{h % 12 or 12}"
    if m:
        label += f":{m:02d}"
    return f"{label} {'AM' if h < 12 else 'PM'}"


def next_run(spec, now=None):
    """spec -> human string like 'tonight 11 PM', or None if unparseable."""
    now = now or datetime.now()
    try:
        days_part, times_part = spec.strip().split(None, 1)
        if days_part.upper() == "DAILY":
            weekdays = set(range(7))
        else:
            weekdays = {_WD[d.strip().upper()[:3]] for d in days_part.split(",")}
        times = []
        for t in times_part.split(","):
            hh, mm = t.strip().split(":")
            times.append((int(hh), int(mm)))
    except (ValueError, KeyError):
        return None

    best = None
    for d in range(0, 8):
        day = now + timedelta(days=d)
        if day.weekday() not in weekdays:
            continue
        for hh, mm in times:
            cand = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand > now and (best is None or cand < best):
                best = cand
    if best is None:
        return None
    d = (best.date() - now.date()).days
    prefix = {0: "tonight" if best.hour >= 17 else "today",
              1: "tomorrow"}.get(d, best.strftime("%a"))
    return f"{prefix} {_ampm(best.hour, best.minute)}"


if __name__ == "__main__":
    import sys
    print(next_run(sys.argv[1]))
