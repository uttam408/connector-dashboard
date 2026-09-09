#!/usr/bin/env python3
"""
backfill_history.py -- one-time (idempotent) seed for docs/history.json.

Every scheduled run has committed docs/status.json, so the repo's own git
history already holds a per-day record of every item's colour. Walk those
commits, take the last one for each calendar day, and fold them into
history.json. Existing entries win, so this is safe to re-run.

    python3 backfill_history.py
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HIST = ROOT / "docs" / "history.json"
REL = "docs/status.json"


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=True).stdout


def main():
    log = git("log", "--format=%H %cI", "--", REL).splitlines()

    by_day = {}                      # date -> sha (last commit of that day wins)
    for line in log:                 # git log is newest-first
        sha, iso = line.split(" ", 1)
        by_day.setdefault(iso[:10], sha)

    hist = {}
    if HIST.exists():
        try:
            hist = json.loads(HIST.read_text())
        except ValueError:
            hist = {}

    added = 0
    for day, sha in by_day.items():
        if day in hist:              # never clobber a real record
            continue
        try:
            blob = git("show", f"{sha}:{REL}")
            payload = json.loads(blob)
        except Exception:            # noqa: BLE001 - old/!parseable revisions
            continue
        # tolerate the older "groups" key as well as today's "sections"
        buckets = payload.get("sections") or payload.get("groups") or []
        hist[day] = {i["label"]: i["color"]
                     for b in buckets for i in b.get("items", [])}
        added += 1

    HIST.write_text(json.dumps(hist, indent=2, sort_keys=True) + "\n")
    print(f"backfilled {added} day(s); history.json now covers "
          f"{len(hist)} day(s): {', '.join(sorted(hist))}")


if __name__ == "__main__":
    main()
