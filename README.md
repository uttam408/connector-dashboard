# connector-dashboard

Daily red/green health check of every connector, credential store, and
launchd agent this Mac depends on &mdash; published as a static dashboard on
GitHub Pages.

**Live:** https://uttam408.github.io/connector-dashboard/

## How it works

| piece | what it does |
|-------|--------------|
| `check.py` | probes each source locally, writes **sanitized** `docs/status.json` + `docs/history.json` |
| `backfill_history.py` | one-time (idempotent) seed of `history.json` from the repo's own `status.json` commits |
| `run.sh` | merges origin/main first (picks up cloud pushes), runs `check.py`, then commits & pushes `docs/` if it changed |
| `com.uttam.connector-dashboard.plist` | launchd agent &mdash; fires `run.sh` daily at **05:00** local |
| `docs/index.html` | zero-dependency text + emoji dashboard that renders `status.json` |

Two sections: **services** (MCP connectors, Tailscale, CLI e-mail, health
APIs, notifications, WhatsApp) and **agents** (launchd jobs).

### The rule

An entry is **green** only if its underlying credential / data / log was
refreshed within the last **24 h** (`CUTOFF_H` in `check.py`). Otherwise
**red**. Live daemons are judged by a health check instead: MCP connectors
via `claude mcp list`, Tailscale via `tailscale status`, and **Garmin** by an
actual ~1s ping (`garminconnect` login from the cached tokenstore + a
`get_full_name()` call). Garmin gets a real ping because it's an on-demand
CLI with no scheduled job — file age would flag it red every day nobody
happened to run it — and because `garminconnect` silently refreshes an
expired access token from the stored refresh token, so an old file is not
evidence of a problem. Whoop's **internal** API deliberately stays on the age
rule: that endpoint has no refresh flow, so staleness there really does mean
"go re-login".

Agents that fire less than daily (`import-downloads-to-photos`, Mon & Thu
23:00) are judged by load state + last exit code, not 24h freshness: green
on a scheduled day if loaded and last exited cleanly, red if the last run
failed — and gray (💤, "skipped") on days they aren't scheduled, so the
history strip doesn't lie. Gray is excluded from the green/red counts.
Intentionally-off entries (`PitchBook Premium`, `checkin-digest` (paused),
`strava-friends-feed`, `battery.plist`) are dimmed, excluded from the
count, and sink to the bottom of their section.

Green rows show only their age (or nothing); red rows stay verbose.

### 5-day lookback

Each row leads with a strip of five squares, oldest → today; the rightmost
square is the current state. `docs/history.json` keeps one record per
calendar day (`{"YYYY-MM-DD": {label: colour}}`, last run of the day wins)
and `check.py` folds the last `LOOKBACK_DAYS` into each item as `history`,
so the page needs no extra fetch. `⬜` means no record for that day — the
item didn't exist yet, or the job didn't run. `💤` means skipped — a
less-than-daily agent on a day it wasn't scheduled. Hover a square for the
date and state. On narrow screens the oldest days drop off via CSS rather
than squashing the label.

`history.json` retains 3× the rendered window, so widening `LOOKBACK_DAYS`
back out doesn't lose days that were already recorded.

_(The Pi RGB-matrix clock check was removed — the `ssh … systemctl is-active`
probe was too flaky. TODO: a reliable heartbeat.)_

### What is published

Only: section name, item label, colour, a short generic note, and a rounded
age. **Never**: file paths, e-mail addresses, ntfy topics, contact names,
message counts, or any message content. Safe for a public repo.

## Setup

```sh
./install.sh                     # symlink + load the launchd agent
launchctl kickstart -k gui/$(id -u)/com.uttam.connector-dashboard   # run now
```

GitHub Pages: repo **Settings -> Pages -> Source: Deploy from a branch ->
`main` / `/docs`**.

## Checked sources

**services:** Claude.ai MCP connectors (Drive, Calendar, Gmail, PitchBook,
Playwright) &middot; Tailscale &middot; `gws` CLI e-mail accounts (personal /
Wharton / secondary) &middot; Whoop (official + internal), Strava, Garmin
tokens &middot; ntfy + iMessage delivery &middot; WhatsApp local DB freshness

**agents:** morning-checkin, checkin-digest, import-downloads-to-photos,
strava-kudos, this dashboard, daily-news-muse (cloud cron run by Muse), plus
the two disabled ones.

`daily-news-muse.log` is a heartbeat only (one timestamp line per run); the
digest content itself is never published.
