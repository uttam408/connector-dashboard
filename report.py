#!/usr/bin/env python3
"""
report.py -- write one status fragment for the connector dashboard, and
optionally commit + push just that file.

    python3 report.py --label "morning-checkin" --section agents \
        --color green --update "digest sent" --next "6 AM" --push

See docs/STATUS-FORMAT.md for the schema. This is the writer for machines that
have the repo checked out (Mac launchd agents). Cloud agents with no working
tree should PUT the same JSON via the GitHub Contents API instead.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
FRAG_DIR = os.path.join(REPO, "docs", "status.d")

# fields that must never carry a path / address / secret / payload
_LEAK = re.compile(
    r"(/Users/|/home/|@[\w.-]+\.\w|GOCSPX-|ntfy\.sh/|xoxb-|ghp_|Bearer )",
    re.I,
)


def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--section", required=True, choices=["services", "agents"])
    ap.add_argument("--color", required=True, choices=["green", "red", "gray"])
    ap.add_argument("--update", default="")
    ap.add_argument("--ts", default=None,
                    help="ISO-8601 with offset; default = now (local)")
    ap.add_argument("--next", dest="next_", default="")
    ap.add_argument("--order", type=int, default=None)
    ap.add_argument("--intentional", action="store_true")
    ap.add_argument("--stale-hours", type=float, default=None)
    ap.add_argument("--push", action="store_true",
                    help="commit just this fragment and push, with retry")
    args = ap.parse_args()

    for name, val in [("update", args.update), ("next", args.next_),
                      ("label", args.label)]:
        if val and _LEAK.search(val):
            sys.exit(f"refusing to publish: --{name} looks like it contains a "
                     f"path / address / secret")

    frag = {"label": args.label, "section": args.section, "color": args.color}
    if args.update:
        frag["update"] = args.update
    frag["ts"] = args.ts or time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if args.next_:
        frag["next"] = args.next_
    if args.order is not None:
        frag["order"] = args.order
    if args.intentional:
        frag["intentional"] = True
    if args.stale_hours is not None:
        frag["stale_hours"] = args.stale_hours

    os.makedirs(FRAG_DIR, exist_ok=True)
    path = os.path.join(FRAG_DIR, slug(args.label) + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(frag, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print(f"wrote {os.path.relpath(path, REPO)}")

    if not args.push:
        return

    def git(*a, check=True):
        return subprocess.run(["git", "-C", REPO, *a], text=True,
                              capture_output=True, check=check)

    rel = os.path.relpath(path, REPO)
    git("fetch", "-q", "origin", "main", check=False)
    git("merge", "-q", "--ff-only", "origin/main", check=False)
    git("add", rel)
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("no change to push")
        return
    git("-c", "user.name=connector-dashboard bot",
        "-c", "user.email=uttam408@users.noreply.github.com",
        "commit", "-q", "-m",
        f"status: {args.label} — {args.update or args.color}")
    for attempt in range(1, 6):
        # another agent may have pushed between our fetch and now
        git("fetch", "-q", "origin", "main", check=False)
        git("rebase", "-q", "origin/main", check=False)
        if git("push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            print(f"pushed (attempt {attempt})")
            return
        time.sleep(15)
    sys.exit("push failed after 5 attempts")


if __name__ == "__main__":
    main()
