#!/usr/bin/env python3
"""
check.py -- probe every connector / credential this Mac can see and append a
run line to its log in docs/status.d/, then trim every log.

Covers only what needs local access: MCP connectors, Tailscale, gws
credential files, Whoop/Strava tokens, a Garmin ping, the WhatsApp DB, and
the launchd agents that don't self-report. Agents that run at other times
append to their own logs (see report.py and docs/STATUS-FORMAT.md); this run
does not touch those beyond trimming.

If this Mac is down, only the rows it owns go stale (correct -- those checks
can't run anywhere else) and logs grow a little (harmless).

Sanitization: logs are public. Only a label, colour, and a short generic
status string ever leave here -- never a path, address, token, ntfy topic,
contact name, or message content.
"""

import glob
import json
import os
import re
import subprocess
import time

REPO = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(REPO, "docs", "status.d")
HOME = os.path.expanduser("~")
NOW = time.time()
TS = time.strftime("%Y-%m-%dT%H:%M:%S%z")
CUTOFF_H = 24
KEEP_RUNS = 60          # run lines retained per log after trim
PATH = os.environ.get("PATH", "") + f":{HOME}/.local/bin:/opt/homebrew/bin"

os.makedirs(DIR, exist_ok=True)


# ---------------------------------------------------------------- helpers ----
def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(epoch))


def record(label, section, color, update="", next_=None, order=500,
           stale_hours=None, ts=None, schedule=None):
    """Ensure a header line, then append one run line. ts defaults to now;
    pass a log's mtime for an agent so 'x ago' means 'when it last ran'.
    schedule ("DAILY 06:00", "MON,THU 23:00") goes on the header -- the page
    computes the concrete next-run live from it, so it never goes stale.
    next_ is a literal one-off override; prefer schedule."""
    path = os.path.join(DIR, slug(label) + ".jsonl")
    header = {"label": label, "section": section, "order": order, "source": "claude"}
    if schedule:
        header["schedule"] = schedule
    if stale_hours is not None:
        header["stale_hours"] = stale_hours

    lines = []
    if os.path.exists(path):
        lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln]
    # line 1 is the header (identified by "label"); refresh it, or prepend it
    if lines and "label" in json.loads(lines[0]):
        lines[0] = json.dumps(header)
    else:
        lines = [json.dumps(header)] + lines

    run = {"ts": ts or TS, "color": color}
    if update:
        run["update"] = update
    if next_:
        run["next"] = next_
    lines.append(json.dumps(run))

    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
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
DIM = {"pitchbook": "not in use right now", "microsoft 365": "never connected"}
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
            label = f"Wharton {label} (MCP)"
        s = status_part.lower()
        if any(k in label.lower() for k in DIM):
            continue                      # dim rows are static .json, not logged
        if "connected" in s and "not" not in s:
            record(label, "services", "green", order=order)
        elif "auth" in s:
            record(label, "services", "red", "needs authentication", order=order)
        else:
            record(label, "services", "red", "unavailable", order=order)
        order += 1
except Exception as e:  # noqa: BLE001
    record("MCP check", "services", "red",
           f"could not run: {type(e).__name__}", order=10)


# ------------------------------------------------------------ Tailscale ----
try:
    j = json.loads(run(["tailscale", "status", "--json"], timeout=20).stdout)
    state = j.get("BackendState")
    online = (j.get("Self") or {}).get("Online")
    if state == "Running" and online:
        peers = len(j.get("Peer") or {})
        record("Tailscale", "services", "green",
               f"{peers} peer" + ("s" if peers != 1 else ""), order=20)
    elif state == "Running":
        record("Tailscale", "services", "red", "running but self offline", order=20)
    else:
        record("Tailscale", "services", "red",
               f"backend {state or 'stopped'}", order=20)
except Exception as e:  # noqa: BLE001
    record("Tailscale", "services", "red",
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
        record(label, "services", "red", "credentials missing — re-auth",
               order=30 + i)
        continue
    h = newest_age(cred, os.path.join(d, "token_cache.json"))
    if h is not None and h < CUTOFF_H:
        record(label, "services", "green", f"token refreshed {rel(h)}", order=30 + i)
    else:
        record(label, "services", "red", f"token stale — {rel(h)}", order=30 + i)


# ------------------------------------------------- health data tools ----
for i, (label, p) in enumerate([
    ("Whoop (official API)", "~/whoop-sync/tokens.json"),
    ("Whoop (internal API)", "~/whoop-unofficial/tokens.json"),
    ("Strava", "~/strava-sync/tokens.json"),
]):
    h = age_hours(p)
    if h is not None and h < CUTOFF_H:
        record(label, "services", "green", f"token refreshed {rel(h)}", order=40 + i)
    else:
        record(label, "services", "red", f"token stale — {rel(h)}", order=40 + i)


# Garmin: on-demand CLI, garminconnect silently refreshes from the stored
# refresh token, so file age is meaningless -- ping for real (~1s).
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
record("Garmin", "services", gc, gu, order=43)


# ---------------------------------------------- notification delivery ----
notif_h = newest_age("~/checkin/checkin.log", "~/Library/Logs/checkin-digest.log")
for i, label in enumerate(("ntfy push", "iMessage")):
    if notif_h is not None and notif_h < CUTOFF_H:
        record(label, "services", "green", f"delivered {rel(notif_h)}", order=50 + i)
    else:
        record(label, "services", "red",
               f"no check-in run in {CUTOFF_H}h ({rel(notif_h)})", order=50 + i)


# --------------------------------------------------------- WhatsApp ----
wa = ("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
      "ChatStorage.sqlite")
h = age_hours(wa)
if h is None:
    record("WhatsApp", "services", "red", "Desktop DB not found", order=55)
elif h < CUTOFF_H:
    record("WhatsApp", "services", "green", f"Desktop synced {rel(h)}", order=55)
else:
    record("WhatsApp", "services", "red",
           f"Desktop not syncing — DB {rel(h)}", order=55)


# ================================================================== AGENTS ==
EXIT_HINTS = {("com.uttam408.strava-kudos", 3): "Strava session expired — re-login"}

DONE_RE = re.compile(r"Done\. Imported: (\d+), Failed: (\d+)\.")


def last_run_summary(log):
    """Pull the last 'Done. Imported: N, Failed: M.' line out of an
    import-downloads-style log, so the row's update text reflects what
    actually happened last time instead of a scheduling comment."""
    try:
        with open(os.path.expanduser(log), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = DONE_RE.search(line)
        if m:
            imported, failed = int(m.group(1)), int(m.group(2))
            if failed:
                return f"{imported} imported, {failed} failed"
            if imported:
                return f"{imported} imported"
            return "nothing to import"
    return None


def check_agent(label, plist_label, log, order, schedule, run_weekdays=None):
    """schedule: recurrence spec ("DAILY 06:00", "MON,THU 23:00") -- stored on
    the header; the page computes the concrete next-run live, so it can't go
    stale (unlike a string computed once here and frozen). run_weekdays: if
    set, the row shows gray on days not in the set instead of red."""
    loaded, last_exit = agent_state(plist_label)
    try:
        log_ts = iso(os.path.getmtime(os.path.expanduser(log)))
    except OSError:
        log_ts = None
    kw = dict(order=order, schedule=schedule)

    if not loaded:
        record(label, "agents", "red", "not loaded", **kw)
    elif last_exit not in (None, 0):
        hint = EXIT_HINTS.get((plist_label, last_exit),
                              f"last run failed (exit {last_exit})")
        record(label, "agents", "red", hint, ts=log_ts, **kw)
    elif run_weekdays is not None:
        scheduled = time.localtime(NOW).tm_wday in run_weekdays
        summary = last_run_summary(log)
        update = summary if summary is not None else (
            "" if scheduled else "not scheduled today")
        record(label, "agents", "green" if scheduled else "gray",
               update, ts=log_ts, **kw)
    else:
        h = age_hours(log)
        if h is not None and h < CUTOFF_H:
            record(label, "agents", "green", "", ts=log_ts, **kw)
        else:
            record(label, "agents", "red",
                   f"no run in {CUTOFF_H}h ({rel(h)})", **kw)


check_agent("morning-checkin", "com.uttam.morning-checkin",
            "~/checkin/checkin.log", order=10,
            schedule="DAILY 06:00,07:00,08:00,09:00")
check_agent("downloads-to-photos", "com.uttam.import-downloads-to-photos",
            "~/Library/Logs/import-downloads-to-photos.log", order=30,
            schedule="MON,THU 23:00", run_weekdays={0, 3})
record("connector-dashboard", "agents", "green", "checked", order=40,
       schedule="DAILY 05:00")

# WRTCbot self-reports its own green/red via report.py on its two real run
# days (Wed 8am email draft, Fri 5pm coffee-sync draft) -- this 5am pass
# only marks the other five days gray so the 5-day strip reads as
# "intentionally off" rather than silently stale. Never overwrite Wed/Fri:
# the self-report is the more accurate signal for those.
if time.localtime(NOW).tm_wday not in (2, 4):  # not Wed(2), not Fri(4)
    record("WRTCbot", "agents", "gray", "not scheduled today",
           order=50, stale_hours=170)


# ------------------------------------------------------------ trim ----
for path in glob.glob(os.path.join(DIR, "*.jsonl")):
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln]
    if len(lines) <= 1 + KEEP_RUNS:
        continue
    kept = [lines[0]] + lines[-KEEP_RUNS:]
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    os.replace(path + ".tmp", path)

print(f"appended + trimmed -> {os.path.relpath(DIR, REPO)}/*.jsonl")
