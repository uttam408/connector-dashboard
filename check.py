#!/usr/bin/env python3
"""
check.py -- probe every connector / credential this machine can see and write
one status fragment per row to docs/status.d/.

This covers only the things that genuinely need local access: MCP connectors,
Tailscale, gws credential files, Whoop/Strava tokens, a Garmin ping, the
WhatsApp DB, and the Mac launchd agents that don't self-report yet. Agents
that run at other times of day write their own fragments (see report.py and
docs/STATUS-FORMAT.md); this run does not touch those.

If this Mac is down, only the rows it owns go stale -- which is correct, since
those checks can't be done from anywhere else.

Sanitization: fragments are published to a public repo. Only a label, colour,
and a short generic status string ever leave here -- never a path, address,
token, ntfy topic, contact name, or message content.
"""

import json
import os
import re
import subprocess
import time

REPO = os.path.dirname(os.path.abspath(__file__))
FRAG_DIR = os.path.join(REPO, "docs", "status.d")
HOME = os.path.expanduser("~")
NOW = time.time()
TS = time.strftime("%Y-%m-%dT%H:%M:%S%z")
CUTOFF_H = 24
PATH = os.environ.get("PATH", "") + f":{HOME}/.local/bin:/opt/homebrew/bin"

os.makedirs(FRAG_DIR, exist_ok=True)


# ---------------------------------------------------------------- helpers ----
def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(epoch))


_UNSET = object()


def emit(label, section, color, update="", next_=None, order=500,
         intentional=False, ts=_UNSET):
    """ts: an ISO string, or None to omit. Agents default to this run's time
    (freshness is the signal); services default to no ts (colour is the
    signal, and the `update` string already carries any age that matters)."""
    if ts is _UNSET:
        ts = None if section == "services" else TS
    frag = {"label": label, "section": section, "color": color}
    if update:
        frag["update"] = update
    if ts:
        frag["ts"] = ts
    if next_:
        frag["next"] = next_
    frag["order"] = order
    if intentional:
        frag["intentional"] = True
    path = os.path.join(FRAG_DIR, slug(label) + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(frag, f, indent=2)
        f.write("\n")
    os.replace(path + ".tmp", path)


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


def run(cmd, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "PATH": PATH})


def agent_state(plist_label):
    """(loaded, last_exit_code) -- exit code None if it never exited."""
    try:
        r = run(["launchctl", "print", f"gui/{os.getuid()}/{plist_label}"],
                timeout=15)
    except Exception:
        return False, None
    if r.returncode != 0:
        return False, None
    m = re.search(r"last exit code\s*=\s*(\d+)", r.stdout)
    return True, (int(m.group(1)) if m else None)


# ================================================================ SERVICES ==

# --------------------------------------------- Claude.ai MCP connectors ----
DIM_CONNECTORS = {
    "pitchbook": "not in use right now",
    "microsoft 365": "never connected",
}
order = 10
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
        dim = next((n for k, n in DIM_CONNECTORS.items() if k in label.lower()),
                   None)
        if dim:
            emit(label, "services", "red", dim, order=900, intentional=True)
        elif "connected" in s and "not" not in s:
            emit(label, "services", "green", order=order)
        elif "auth" in s:
            emit(label, "services", "red", "needs authentication", order=order)
        else:
            emit(label, "services", "red", "unavailable", order=order)
        order += 1
except Exception as e:  # noqa: BLE001
    emit("MCP check", "services", "red",
         f"could not run: {type(e).__name__}", order=10)


# ------------------------------------------------------------ Tailscale ----
try:
    j = json.loads(run(["tailscale", "status", "--json"], timeout=20).stdout)
    state = j.get("BackendState")
    online = (j.get("Self") or {}).get("Online")
    if state == "Running" and online:
        peers = len(j.get("Peer") or {})
        emit("Tailscale", "services", "green",
             f"{peers} peer" + ("s" if peers != 1 else ""), order=20)
    elif state == "Running":
        emit("Tailscale", "services", "red", "running but self offline", order=20)
    else:
        emit("Tailscale", "services", "red",
             f"backend {state or 'stopped'}", order=20)
except Exception as e:  # noqa: BLE001
    emit("Tailscale", "services", "red",
         f"not reachable: {type(e).__name__}", order=20)


# --------------------------------------------------- gws CLI e-mail ----
for i, (label, d) in enumerate([
    ("Personal Gmail (CLI)", "~/.config/gws"),
    ("Wharton Gmail (CLI)", "~/.config/gws-wharton"),
    ("Secondary Gmail (CLI)", "~/.config/gws-unitedhvy"),
]):
    d = os.path.expanduser(d)
    cred = os.path.join(d, "credentials.enc")
    if not os.path.exists(cred):
        emit(label, "services", "red", "credentials missing — re-auth",
             order=30 + i)
        continue
    h = newest_age(cred, os.path.join(d, "token_cache.json"))
    if h is not None and h < CUTOFF_H:
        emit(label, "services", "green", f"token refreshed {rel(h)}", order=30 + i)
    else:
        emit(label, "services", "red", f"token stale — {rel(h)}", order=30 + i)


# ------------------------------------------------- health data tools ----
for i, (label, p, verb) in enumerate([
    ("Whoop (official API)", "~/whoop-sync/tokens.json", "token refreshed"),
    # no refresh flow for the internal endpoint -- staleness genuinely means
    # "go re-login", so it stays on the age rule
    ("Whoop (internal API)", "~/whoop-unofficial/tokens.json", "token refreshed"),
    ("Strava", "~/strava-sync/tokens.json", "token refreshed"),
]):
    h = age_hours(p)
    if h is not None and h < CUTOFF_H:
        emit(label, "services", "green", f"{verb} {rel(h)}", order=40 + i)
    else:
        emit(label, "services", "red",
             f"stale — last {verb.split()[-1]} {rel(h)}", order=40 + i)


# Garmin: on-demand CLI, no scheduled job, and garminconnect silently refreshes
# an expired access token from the stored refresh token -- so file age is
# meaningless. Ping it for real (~1s).
def garmin_ping():
    py = os.path.expanduser("~/garmin-sync/venv/bin/python")
    store = os.path.expanduser("~/garmin-sync/.garmintokens")
    if not os.path.exists(py):
        return "red", "sync tool not installed"
    probe = ("import garminconnect;c=garminconnect.Garmin();"
             f"c.login(tokenstore={store!r});print(c.get_full_name())")
    try:
        r = subprocess.run([py, "-c", probe], capture_output=True, text=True,
                           timeout=60)
    except subprocess.TimeoutExpired:
        return "red", "ping timed out"
    if r.returncode == 0 and r.stdout.strip():
        return "green", "ping ok"
    tail = ((r.stderr or "").strip().splitlines() or ["unknown error"])[-1][:60]
    if "login" in tail.lower() or "auth" in tail.lower():
        return "red", "session expired — re-login"
    return "red", f"ping failed: {tail}"


gc, gu = garmin_ping()
emit("Garmin", "services", gc, gu, order=43)


# ---------------------------------------------- notification delivery ----
# morning-checkin and (when not paused) checkin-digest push via the same
# ntfy + iMessage notifiers -- freshness = the most recent of the two.
notif_h = newest_age("~/checkin/checkin.log", "~/Library/Logs/checkin-digest.log")
for i, label in enumerate(("ntfy push", "iMessage")):
    if notif_h is not None and notif_h < CUTOFF_H:
        emit(label, "services", "green", f"delivered {rel(notif_h)}", order=50 + i)
    else:
        emit(label, "services", "red",
             f"no check-in run in {CUTOFF_H}h ({rel(notif_h)})", order=50 + i)


# --------------------------------------------------------- WhatsApp ----
wa = ("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
      "ChatStorage.sqlite")
h = age_hours(wa)
if h is None:
    emit("WhatsApp", "services", "red", "Desktop DB not found", order=55)
elif h < CUTOFF_H:
    emit("WhatsApp", "services", "green", f"Desktop synced {rel(h)}", order=55)
else:
    emit("WhatsApp", "services", "red",
         f"Desktop not syncing — DB {rel(h)}", order=55)


# ================================================================== AGENTS ==
# Only the Mac launchd agents that don't self-report yet. morning-checkin also
# self-reports at 6-9am (that fragment wins during the day); this 5am pass is
# the backstop that catches it if it stops running entirely.

EXIT_HINTS = {("com.uttam408.strava-kudos", 3): "Strava session expired — re-login"}


def check_agent(label, plist_label, log, order, next_=None, run_weekdays=None):
    loaded, last_exit = agent_state(plist_label)
    log_epoch = None
    try:
        log_epoch = os.path.getmtime(os.path.expanduser(log))
    except OSError:
        pass
    log_ts = iso(log_epoch) if log_epoch else None

    if not loaded:
        emit(label, "agents", "red", "not loaded", order=order, next_=next_)
    elif last_exit not in (None, 0):
        hint = EXIT_HINTS.get((plist_label, last_exit),
                              f"last run failed (exit {last_exit})")
        emit(label, "agents", "red", hint, order=order, next_=next_, ts=log_ts)
    elif run_weekdays is not None:
        # less-than-daily: judged by load + clean exit only, not freshness;
        # gray on days it isn't scheduled so the strip doesn't imply a miss
        if time.localtime(NOW).tm_wday in run_weekdays:
            emit(label, "agents", "green", "", order=order, next_=next_, ts=log_ts)
        else:
            emit(label, "agents", "gray", "not scheduled today",
                 order=order, next_=next_, ts=log_ts)
    else:
        h = age_hours(log)
        if h is not None and h < CUTOFF_H:
            emit(label, "agents", "green", "", order=order, next_=next_, ts=log_ts)
        else:
            emit(label, "agents", "red",
                 f"no run in {CUTOFF_H}h ({rel(h)})", order=order, next_=next_)


check_agent("morning-checkin", "com.uttam.morning-checkin",
            "~/checkin/checkin.log", order=10, next_="6 AM")
check_agent("import-downloads-to-photos", "com.uttam.import-downloads-to-photos",
            "~/Library/Logs/import-downloads-to-photos.log", order=30,
            next_="Mon & Thu 23:00", run_weekdays={0, 3})

# connector-dashboard reporting its own run
emit("connector-dashboard", "agents", "green", "checked", order=40, next_="5 AM")

print(f"wrote fragments -> {os.path.relpath(FRAG_DIR, REPO)}/")
