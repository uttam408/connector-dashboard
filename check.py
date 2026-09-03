#!/usr/bin/env python3
"""
check.py -- probe every service / credential / launchd agent this machine
depends on and emit a SANITIZED status file for the GitHub Pages dashboard.

Rule: an entry is GREEN only if it has been refreshed within the last 24h
(CUTOFF_H). Otherwise RED. Live daemons (MCP connectors, Tailscale, the Pi
clock) are judged by a health check instead. Intentionally-off entries are
marked so the page can dim them.

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
        if "pitchbook" in label.lower():
            services.append(item(label, "red", "not in use right now",
                                 intentional=True))
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


# ------------------------------------------------- Pi RGB-matrix clock ----
# Physical 64x64 LED matrix clock on the Raspberry Pi (led-clock.service).
# Reach it over the LAN first, then Tailscale; SSH key is passphrase-free.
def clock_status():
    cmd = "systemctl is-active led-clock.service"
    for host in ("pi-lan", "pi"):
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
                 "-o", "StrictHostKeyChecking=accept-new", host, cmd],
                capture_output=True, text=True, timeout=25,
            )
        except Exception:
            continue
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out == "active":
            return item("Clock display", "green", "")
        if out:                       # reachable, some other unit state
            return item("Clock display", "red", f"led-clock {out}")
    return item("Clock display", "red", "Pi unreachable")


services.append(clock_status())


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
    ("Whoop (internal API)", "~/whoop-unofficial/tokens.json"),
    ("Strava", "~/strava-sync/tokens.json"),
    ("Garmin", "~/garmin-sync/.garmintokens/garmin_tokens.json"),
]:
    h = age_hours(p)
    c, note = fresh(h, "token refresh")
    services.append(item(label, c, note, h))


# ---------------------------------------------- notification delivery ----
digest_log = "~/Library/Logs/checkin-digest.log"
for label in ("ntfy push", "iMessage notifier"):
    h = age_hours(digest_log)
    if h is not None and h < CUTOFF_H:
        services.append(item(label, "green", rel(h), h))
    else:
        services.append(item(label, "red",
                             f"no check-in digest in {CUTOFF_H}h ({rel(h)})", h))


# --------------------------------------------------------- WhatsApp ----
wa = ("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
      "ChatStorage.sqlite")
h = age_hours(wa)
if h is None:
    services.append(item("WhatsApp (local DB)", "red", "Desktop DB not found"))
elif h < CUTOFF_H:
    services.append(item("WhatsApp (local DB)", "green", rel(h), h))
else:
    services.append(item("WhatsApp (local DB)", "red",
                         f"Desktop not syncing — DB {rel(h)}", h))


# --------------------------------------------------- launchd agents ----
# (label, plist label, log path, schedule_note | False)
# an agent with a schedule_note fires less than daily -- judge it by whether
# it's loaded and last exited cleanly, not by 24h freshness.
AGENTS = [
    ("morning-checkin", "com.uttam.morning-checkin", "~/checkin/launchd.log", False),
    ("checkin-digest", "com.uttam.checkin-digest",
     "~/Library/Logs/checkin-digest.log", False),
    ("import-downloads-to-photos", "com.uttam.import-downloads-to-photos",
     "~/Library/Logs/import-downloads-to-photos.log", "Mon & Thu 23:00"),
    ("strava-kudos", "com.uttam408.strava-kudos",
     "~/Library/Mobile Documents/com~apple~CloudDocs/strava-friends-feed/kudos.log",
     False),
    ("connector-dashboard", "com.uttam.connector-dashboard",
     "~/Library/Logs/connector-dashboard.log", False),
]
for label, plist_label, log, sched_note in AGENTS:
    loaded, last_exit = agent_state(plist_label)
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
    if h is not None and h < CUTOFF_H:
        agents.append(item(label, "green", rel(h), h))
    else:
        agents.append(item(label, "red", f"no run in {CUTOFF_H}h ({rel(h)})", h))

agents.append(item("strava-friends-feed", "red",
                   "disabled — replaced by strava-kudos", intentional=True))
agents.append(item("battery.plist", "red",
                   "not loaded — app self-manages", intentional=True))


# ------------------------------------------------------------- write ----
payload = {
    "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)),
    "cutoff_hours": CUTOFF_H,
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
