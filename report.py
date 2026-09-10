#!/usr/bin/env python3
"""
report.py -- append one run line to a status log for the connector dashboard,
and optionally commit + push just that file.

    python3 report.py --label "morning-checkin" --section agents \
        --color green --update "digest sent" --next "6 AM" --push

The log is docs/status.d/<slug>.jsonl: line 1 a header {label, section,
order, stale_hours}, every line after it a run {ts, color, update?, next?}.
Writers only ever append -- check.py trims the file centrally. Concurrent
appends auto-merge (see .gitattributes: *.jsonl merge=union), so --push is
just `commit; pull --rebase; push`.

See docs/STATUS-FORMAT.md. Cloud agents with a checkout do the same
`echo >> ; git commit ; git push`; the schema is the contract, not this
script.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(REPO, "docs", "status.d")

_LEAK = re.compile(
    r"(/Users/|/home/|@[\w.-]+\.\w|GOCSPX-|ntfy\.sh/|xoxb-|ghp_|Bearer )", re.I)


def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--section", required=True, choices=["services", "agents"])
    ap.add_argument("--color", required=True, choices=["green", "red", "gray"])
    ap.add_argument("--update", default="")
    ap.add_argument("--ts", default=None, help="ISO-8601 w/ offset; default now")
    ap.add_argument("--next", dest="next_", default="")
    ap.add_argument("--order", type=int, default=500)
    ap.add_argument("--stale-hours", type=float, default=None)
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    for name, val in [("update", args.update), ("next", args.next_),
                      ("label", args.label)]:
        if val and _LEAK.search(val):
            sys.exit(f"refusing to publish: --{name} looks like a "
                     f"path / address / secret")

    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, slug(args.label) + ".jsonl")

    header = {"label": args.label, "section": args.section, "order": args.order}
    if args.stale_hours is not None:
        header["stale_hours"] = args.stale_hours
    run = {"ts": args.ts or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "color": args.color}
    if args.update:
        run["update"] = args.update
    if args.next_:
        run["next"] = args.next_

    lines = []
    if os.path.exists(path):
        lines = [ln for ln in open(path, encoding="utf-8").read().splitlines()
                 if ln]
    if lines and "label" in json.loads(lines[0]):
        lines[0] = json.dumps(header)
    else:
        lines.insert(0, json.dumps(header))
    lines.append(json.dumps(run))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"appended to {os.path.relpath(path, REPO)}")

    if not args.push:
        return

    def git(*a, check=True):
        return subprocess.run(["git", "-C", REPO, *a], text=True,
                              capture_output=True, check=check)

    rel = os.path.relpath(path, REPO)
    git("add", rel)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no change")
        return
    git("-c", "user.name=connector-dashboard bot",
        "-c", "user.email=uttam408@users.noreply.github.com",
        "commit", "-q", "-m", f"status: {args.label} — {args.update or args.color}")
    for attempt in range(1, 6):
        git("fetch", "-q", "origin", "main", check=False)
        git("rebase", "-q", "origin/main", check=False)
        if git("push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            print(f"pushed (attempt {attempt})")
            return
        time.sleep(15)
    sys.exit("push failed after 5 attempts")


if __name__ == "__main__":
    main()
