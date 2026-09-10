#!/usr/bin/env python3
"""
check.py -- probe every service / credential / launchd agent this machine
depends on and emit a SANITIZED status file for the GitHub Pages dashboard.

Rule: an entry is GREEN only if it has been refreshed within the last 24h
(CUTOFF_H). Otherwise RED. Live daemons (MCP connectors, Tailscale) are
judged by a health check instead. Intentionally-off entries are marked so
the page can dim them, and sink to the bottom of their section.

Green rows carry a terse note (just the age, or nothing). Red rows stay
verbose so the reason is obvious.

Sanitization: the JSON written to docs/status.json contains only a label,
a colour, a short generic note, and a rounded age. No file paths, e-mail
addresses, ntfy topics, contact names, or message counts ever leave here.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

CUTOFF_H = 24
HOME = Path.home()
OUT = Path(__file__).resolve().parent / "docs" / "status.json"
HIST = Path(__file__).resolve().parent / "docs" / "history.json"
NOW = time.time()
PATH = os.environ.get("PATH", "") + f":{HOME}/.local/bin:/opt/homebrew/bin"


# ---------------------------------------------------------------- helpers ----
def age_hours(path):
    try:
        return (NOW - os.path.getmtime(os.path.expanduser(path))) / 3600.0
    except OSError:
        return None


def newest_age(*paths):
    ages = [a for a in (age_hours(p) for p in paths) if a is not None]
    return min(ages) if ages else None


def rel(h):
    if h is None:
        return "never"
    if h < 1:
        return f"{max(1, int(round(h * 60)))}m ago"
    if h < 48:
        return f"{int(round(h))}h ago"
    return f"{int(round(h / 24))}d ago"


def fresh(h, verb="refreshed"):
    """(colour, terse-or-verbose note) from freshness alone."""
    if h is None:
        return "red", "no data found"
    if h < CUTOFF_H:
        return "green", rel(h)                     # terse
    return "red", f"last {verb} {rel(h)}"          # verbose


def run(cmd, timeout=90):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "PATH": PATH},
    )


def agent_state(label):
    """(loaded, last_exit_code) -- last_exit_code is None if it never exited."""
    try:
        r = run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], timeout=15)
    except Exception:
        return False, None
    if r.returncode != 0:
        return False, None
    m = re.search(r"last exit code\s*=\s*(\d+)", r.stdout)
    return True, (int(m.group(1)) if m else None)


def item(label, color, note, h=None, intentional=False):
    d = {"label": label, "color": color, "note": note}
    if h is not None:
        d["age_hours"] = round(h, 1)
    if intentional:
        d["intentional"] = True
    return d


services = []
agents = []


# --------------------------------------------- Claude.ai MCP connectors ----
# MCP connectors that are deliberately not in use -- shown red but dimmed,
# excluded from the count, and sunk to the bottom of the section.
DIM_CONNECTORS = {
    "pitchbook": "not in use right now",
    "microsoft 365": "never connected",
}

try:
    text = run(["claude", "mcp", "list"]).stdout
    for line in text.splitlines():
        line = line.strip()
        if " - " not in line or ":" not in line:
            continue
        name_part, status_part = line.rsplit(" - ", 1)
        segs = name_part.split(":")
        label = segs[2].strip() if segs[0].strip() == "plugin" and len(segs) > 2 \
            else segs[0].strip()
        label = label.replace("claude.ai ", "").strip()
        if label:
            label = label[0].upper() + label[1:]
        if label.lower() in ("gmail", "google calendar", "google drive"):
            label += " (MCP)"
        s = status_part.lower()
        dim = next((note for key, note in DIM_CONNECTORS.items()
                    if key in label.lower()), None)
        if dim:
            services.append(item(label, "red", dim, intentional=True))
        elif "connected" in s and "not" not in s:
            services.append(item(label, "green", ""))          # terse
        elif "auth" in s:
            services.append(item(label, "red", "needs authentication"))
        else:
            services.append(item(label, "red", "unavailable"))
except Exception as e:  # noqa: BLE001
    services.append(item("MCP check", "red", f"could not run: {type(e).__name__}"))


# ------------------------------------------------------------ Tailscale ----
try:
    j = json.loads(run(["tailscale", "status", "--json"], timeout=20).stdout)
    state = j.get("BackendState")
    online = (j.get("Self") or {}).get("Online")
    if state == "Running" and online:
        peers = len(j.get("Peer") or {})
        services.append(item("Tailscale", "green",
                             f"{peers} peer" + ("s" if peers != 1 else "")))
    elif state == "Running":
        services.append(item("Tailscale", "red", "running but self offline"))
    else:
        services.append(item("Tailscale", "red", f"backend {state or 'stopped'}"))
except Exception as e:  # noqa: BLE001
    services.append(item("Tailscale", "red", f"not reachable: {type(e).__name__}"))


# TODO: Pi RGB-matrix clock (led-clock.service) -- the plain `ssh ...
# systemctl is-active` probe was too flaky (LAN/Tailscale both time out
# intermittently even while the clock is visibly running). Removed until
# there's a reliable signal (e.g. the Pi POSTing a heartbeat somewhere).


# --------------------------------------------------- gws CLI e-mail ----
for label, d in [
    ("Personal Gmail (CLI)", "~/.config/gws"),
    ("Wharton Gmail (CLI)", "~/.config/gws-wharton"),
    ("Secondary Gmail (CLI)", "~/.config/gws-unitedhvy"),
]:
    d = os.path.expanduser(d)
    cred = os.path.join(d, "credentials.enc")
    if not os.path.exists(cred):
        services.append(item(label, "red", "credentials missing — re-auth"))
        continue
    h = newest_age(cred, os.path.join(d, "token_cache.json"))
    c, note = fresh(h, "token refresh")
    services.append(item(label, c, note, h))


# ------------------------------------------------- health data tools ----
for label, p in [
    ("Whoop (official API)", "~/whoop-sync/tokens.json"),
    # no refresh flow for the internal endpoint -- staleness really does mean
    # "go re-login", so this one stays on the age rule
    ("Whoop (internal API)", "~/whoop-unofficial/tokens.json"),
    ("Strava", "~/strava-sync/tokens.json"),
]:
    h = age_hours(p)
    c, note = fresh(h, "token refresh")
    services.append(item(label, c, note, h))


# Garmin is an on-demand CLI with no scheduled job, so file age says nothing
# useful -- and garminconnect silently refreshes an expired access token from
# the stored refresh token. Ping it for real instead (~1s).
def garmin_ping():
    py = os.path.expanduser("~/garmin-sync/venv/bin/python")
    store = os.path.expanduser("~/garmin-sync/.garmintokens")
    if not os.path.exists(py):
        return item("Garmin", "red", "sync tool not installed")
    probe = (
        "import garminconnect;"
        "c=garminconnect.Garmin();"
        f"c.login(tokenstore={store!r});"
        "print(c.get_full_name())"
    )
    try:
        r = subprocess.run([py, "-c", probe], capture_output=True,
                           text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return item("Garmin", "red", "ping timed out")
    if r.returncode == 0 and r.stdout.strip():
        return item("Garmin", "green", "")
    err = (r.stderr or "").strip().splitlines()
    tail = err[-1][:60] if err else "unknown error"
    if "login" in tail.lower() or "auth" in tail.lower():
        return item("Garmin", "red", "session expired — re-login")
    return item("Garmin", "red", f"ping failed: {tail}")


services.append(garmin_ping())


# ---------------------------------------------- notification delivery ----
# morning-checkin and (when not paused) checkin-digest both push via the
# same ntfy + iMessage notifiers -- freshness = the most recent of the two.
# NB: ~/checkin/launchd.log is launchd's stdout redirect and is always 0
# bytes -- detect_and_send.py writes its own checkin.log. Watch that one.
notif_h = newest_age("~/checkin/checkin.log", "~/Library/Logs/checkin-digest.log")
for label in ("ntfy push", "iMessage"):
    if notif_h is not None and notif_h < CUTOFF_H:
        services.append(item(label, "green", rel(notif_h), notif_h))
    else:
        services.append(item(label, "red",
                             f"no check-in run in {CUTOFF_H}h ({rel(notif_h)})", notif_h))


# --------------------------------------------------------- WhatsApp ----
wa = ("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
      "ChatStorage.sqlite")
h = age_hours(wa)
if h is None:
    services.append(item("WhatsApp", "red", "Desktop DB not found"))
elif h < CUTOFF_H:
    services.append(item("WhatsApp", "green", rel(h), h))
else:
    services.append(item("WhatsApp", "red",
                         f"Desktop not syncing — DB {rel(h)}", h))


# --------------------------------------------------- launchd agents ----
# (label, plist label, log path, schedule_note | False)
# an agent with a schedule_note fires less than daily -- judge it by whether
# it's loaded and last exited cleanly, not by 24h freshness.
AGENTS = [
    # checkin.log, not launchd.log -- see the note by notif_h above
    ("morning-checkin", "com.uttam.morning-checkin", "~/checkin/checkin.log", False),
    ("checkin-digest", "com.uttam.checkin-digest",
     "~/Library/Logs/checkin-digest.log", False),
    ("import-downloads-to-photos", "com.uttam.import-downloads-to-photos",
     "~/Library/Logs/import-downloads-to-photos.log", "Mon & Thu 23:00"),
    # log lives outside iCloud -- launchd can't open evicted files
    ("strava-kudos", "com.uttam408.strava-kudos",
     "~/Library/Logs/strava-kudos.log", False),
    ("connector-dashboard", "com.uttam.connector-dashboard",
     "~/Library/Logs/connector-dashboard.log", False),
]
# agents deliberately paused -- red, but dimmed and excluded from the count
PAUSED = {"com.uttam.checkin-digest"}

# readable notes for known non-zero exit codes; anything else shows the code
EXIT_HINTS = {
    ("com.uttam408.strava-kudos", 3): "Strava session expired — re-login",
}

for label, plist_label, log, sched_note in AGENTS:
    loaded, last_exit = agent_state(plist_label)
    if plist_label in PAUSED:
        agents.append(item(label, "red", "paused", intentional=True))
        continue
    if not loaded:
        agents.append(item(label, "red", "not loaded"))
        continue
    if sched_note:
        if last_exit in (None, 0):
            agents.append(item(label, "green", sched_note))
        else:
            agents.append(item(label, "red", f"last run failed (exit {last_exit})"))
        continue
    h = age_hours(log)
    # a fresh log only proves it ran -- a failed run writes one too
    if last_exit not in (None, 0):
        hint = EXIT_HINTS.get((plist_label, last_exit),
                              f"last run failed (exit {last_exit})")
        agents.append(item(label, "red", hint, h))
    elif h is not None and h < CUTOFF_H:
        agents.append(item(label, "green", rel(h), h))
    else:
        agents.append(item(label, "red", f"no run in {CUTOFF_H}h ({rel(h)})", h))

# not built yet -- placeholder to keep it on the radar
agents.append(item("WRTCbot", "red", "not set up — weekly run email still manual"))

agents.append(item("strava-friends-feed", "red",
                   "disabled — replaced by strava-kudos", intentional=True))
agents.append(item("battery.plist", "red",
                   "not loaded — app self-manages", intentional=True))

# strava-kudos-muse: cloud cron run by Muse (not a Mac launchd agent).
# Health = freshness of its run log in the private shared-context repo.
# Clone that repo to ~/shared-context on this Mac for this check to go green.
_skm = os.path.expanduser("~/shared-context/strava-kudos-muse.md")
_skm_h = age_hours(_skm)
if _skm_h is None:
    agents.append(item("strava-kudos-muse", "grey", "no local mirror"))
elif _skm_h < 80:
    agents.append(item("strava-kudos-muse", "green", rel(_skm_h), _skm_h))
else:
    agents.append(item("strava-kudos-muse", "red",
                       f"no run in 80h ({rel(_skm_h)})", _skm_h))


# dimmed / intentionally-off entries sink to the bottom of their section
def sink(lst):
    return ([i for i in lst if not i.get("intentional")] +
            [i for i in lst if i.get("intentional")])


services = sink(services)
agents = sink(agents)


# ------------------------------------------- 7-day per-item lookback ----
# HIST maps "YYYY-MM-DD" (local) -> {label: "green"|"red"}. One entry per
# day; a second run the same day overwrites it. Each item then carries a
# `history` list of LOOKBACK_DAYS colours, oldest first, None where we have
# no record, so the page can draw a strip of squares with no extra fetch.
LOOKBACK_DAYS = 5
today = time.strftime("%Y-%m-%d", time.localtime(NOW))

hist = {}
if HIST.exists():
    try:
        hist = json.loads(HIST.read_text())
    except ValueError:
        hist = {}

hist[today] = {i["label"]: i["color"]
               for s in (services, agents) for i in s}
# keep a little more than we render, so widening LOOKBACK_DAYS isn't lossy
for stale in sorted(hist)[:-(LOOKBACK_DAYS * 3)]:
    del hist[stale]
HIST.write_text(json.dumps(hist, indent=2, sort_keys=True) + "\n")

days = [time.strftime("%Y-%m-%d",
                      time.localtime(NOW - d * 86400))
        for d in range(LOOKBACK_DAYS - 1, -1, -1)]
for section in (services, agents):
    for i in section:
        i["history"] = [hist.get(d, {}).get(i["label"]) for d in days]


# ------------------------------------------------------------- write ----
payload = {
    "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)),
    "cutoff_hours": CUTOFF_H,
    "lookback_days": LOOKBACK_DAYS,
    "sections": [
        {"name": "services", "items": services},
        {"name": "agents", "items": agents},
    ],
}
OUT.write_text(json.dumps(payload, indent=2) + "\n")

g = sum(1 for s in payload["sections"] for i in s["items"]
        if i["color"] == "green" and not i.get("intentional"))
r = sum(1 for s in payload["sections"] for i in s["items"]
        if i["color"] == "red" and not i.get("intentional"))
print(f"{g} green / {r} red  ->  {OUT}")
