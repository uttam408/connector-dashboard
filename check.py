#!/usr/bin/env python3
"""
check.py -- probe every connector / credential / launchd agent this machine
depends on and emit a SANITIZED status file for the public GitHub Pages
dashboard.

Rule: a source is GREEN only if it has been refreshed within the last 24h
(CUTOFF_H). Otherwise RED. A handful of entries are judged by liveness
(MCP health check) or are intentionally-off (disabled agents) -- those are
marked so they don't pollute the score.

Sanitization: the JSON written to docs/status.json contains only a label,
a colour, a short generic note, and a rounded age. No file paths, e-mail
addresses, ntfy topics, contact names, or message counts ever leave this
script.
"""

import json
import os
import subprocess
import time
from pathlib import Path

CUTOFF_H = 24
HOME = Path.home()
OUT = Path(__file__).resolve().parent / "docs" / "status.json"
HIST = Path(__file__).resolve().parent / "docs" / "history.jsonl"
NOW = time.time()


# ---------------------------------------------------------------- helpers ----
def age_hours(path):
    """Hours since *path* was last modified, or None if it doesn't exist."""
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
        return f"{int(h * 60)}m ago"
    if h < 48:
        return f"{int(round(h))}h ago"
    return f"{int(round(h / 24))}d ago"


def by_age(h, ok_note="refreshed"):
    """Colour purely from freshness."""
    if h is None:
        return "red", "no data found"
    if h < CUTOFF_H:
        return "green", f"{ok_note} {rel(h)}"
    return "red", f"last {ok_note.split()[0]} {rel(h)}"


def agent_loaded(label):
    try:
        uid = os.getuid()
        r = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


groups = []


def group(name, items):
    groups.append({"name": name, "items": items})


def item(label, color, note, h=None, intentional=False):
    d = {"label": label, "color": color, "note": note}
    if h is not None:
        d["age_hours"] = round(h, 1)
    if intentional:
        d["intentional"] = True
    return d


# ------------------------------------------------ 1. claude.ai MCP connectors ----
def check_mcp():
    items = []
    try:
        r = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "PATH": os.environ.get("PATH", "") +
                 f":{HOME}/.local/bin"},
        )
        text = r.stdout
    except Exception as e:  # noqa: BLE001
        return [item("MCP check", "red", f"could not run: {type(e).__name__}")]

    for line in text.splitlines():
        line = line.strip()
        if " - " not in line or ":" not in line:
            continue
        name_part, status_part = line.rsplit(" - ", 1)
        segs = name_part.split(":")
        # "plugin:playwright:playwright: npx ..." -> "playwright"
        label = segs[2].strip() if segs[0].strip() == "plugin" and len(segs) > 2 \
            else segs[0].strip()
        label = label.replace("claude.ai ", "").strip()
        if label:
            label = label[0].upper() + label[1:]
        s = status_part.lower()
        if "connected" in s and "not" not in s:
            items.append(item(label, "green", "connected (live check)"))
        elif "auth" in s:
            items.append(item(label, "red", "needs authentication"))
        else:
            items.append(item(label, "red", "unavailable"))
    return items or [item("MCP check", "red", "no connectors listed")]


group("Claude.ai MCP connectors", check_mcp())


# ---------------------------------------------------- 2. gws CLI e-mail ----
gws_items = []
for label, d in [
    ("Personal Gmail (CLI)", "~/.config/gws"),
    ("Wharton Gmail (CLI)", "~/.config/gws-wharton"),
    ("Secondary Gmail (CLI)", "~/.config/gws-unitedhvy"),
]:
    d = os.path.expanduser(d)
    cred = os.path.join(d, "credentials.enc")
    if not os.path.exists(cred):
        gws_items.append(item(label, "red", "credentials missing -- re-auth needed"))
        continue
    h = newest_age(cred, os.path.join(d, "token_cache.json"))
    c, note = by_age(h, "token refreshed")
    gws_items.append(item(label, c, note, h))
group("CLI e-mail access (gws)", gws_items)


# ------------------------------------------------- 3. health data tools ----
health_items = []
for label, p in [
    ("Whoop (official API)", "~/whoop-sync/tokens.json"),
    ("Whoop (internal API)", "~/whoop-unofficial/tokens.json"),
    ("Strava", "~/strava-sync/tokens.json"),
    ("Garmin", "~/garmin-sync/.garmintokens/garmin_tokens.json"),
]:
    h = age_hours(p)
    c, note = by_age(h, "token refreshed")
    health_items.append(item(label, c, note, h))
group("Health data tools", health_items)


# ---------------------------------------------- 4. notification delivery ----
digest_log = "~/Library/Logs/checkin-digest.log"
notif_items = []
for label in ("ntfy push", "iMessage notifier"):
    h = age_hours(digest_log)
    if h is not None and h < CUTOFF_H:
        notif_items.append(item(label, "green",
                                f"delivered via check-in digest {rel(h)}", h))
    else:
        notif_items.append(item(label, "red",
                                f"no digest run in {CUTOFF_H}h ({rel(h)})", h))
group("Notification delivery", notif_items)


# --------------------------------------------------------- 5. WhatsApp ----
wa = ("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
      "ChatStorage.sqlite")
h = age_hours(wa)
if h is None:
    wa_item = item("WhatsApp (local DB)", "red", "WhatsApp Desktop DB not found")
elif h < CUTOFF_H:
    wa_item = item("WhatsApp (local DB)", "green", f"Desktop synced {rel(h)}", h)
else:
    wa_item = item("WhatsApp (local DB)", "red",
                   f"Desktop not syncing -- DB {rel(h)}; open the app", h)
group("WhatsApp", [wa_item])


# --------------------------------------------------- 6. launchd agents ----
agent_items = []
AGENTS = [
    ("morning-checkin", "com.uttam.morning-checkin", "~/checkin/launchd.log"),
    ("checkin-digest", "com.uttam.checkin-digest",
     "~/Library/Logs/checkin-digest.log"),
    ("import-downloads-to-photos", "com.uttam.import-downloads-to-photos",
     "~/Library/Logs/import-downloads-to-photos.log"),
    ("strava-kudos", "com.uttam408.strava-kudos",
     "~/Library/Mobile Documents/com~apple~CloudDocs/strava-friends-feed/kudos.log"),
    ("connector-dashboard", "com.uttam.connector-dashboard",
     "~/Library/Logs/connector-dashboard.log"),
]
for label, plist_label, log in AGENTS:
    if not agent_loaded(plist_label):
        agent_items.append(item(label, "red", "not loaded"))
        continue
    h = age_hours(log)
    if h is not None and h < CUTOFF_H:
        agent_items.append(item(label, "green", f"ran {rel(h)}", h))
    else:
        agent_items.append(item(label, "red",
                                f"no run in {CUTOFF_H}h ({rel(h)})", h))

agent_items.append(item("strava-friends-feed", "red",
                        "disabled -- replaced by strava-kudos", intentional=True))
agent_items.append(item("battery.plist", "red",
                        "not loaded -- app self-manages", intentional=True))
group("launchd agents", agent_items)


# ------------------------------------------------------------- write ----
scored = [it for g in groups for it in g["items"] if not it.get("intentional")]
green = sum(1 for it in scored if it["color"] == "green")
red = sum(1 for it in scored if it["color"] == "red")

payload = {
    "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)),
    "cutoff_hours": CUTOFF_H,
    "summary": {"green": green, "red": red, "total": green + red},
    "groups": groups,
}

OUT.write_text(json.dumps(payload, indent=2) + "\n")

row = json.dumps({"t": payload["generated"], "green": green, "red": red})
lines = HIST.read_text().splitlines() if HIST.exists() else []
lines.append(row)
HIST.write_text("\n".join(lines[-120:]) + "\n")

print(f"{green} green / {red} red  ->  {OUT}")
