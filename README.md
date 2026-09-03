# connector-dashboard

Daily red/green health check of every connector, credential store, and
launchd agent this Mac depends on &mdash; published as a static dashboard on
GitHub Pages.

**Live:** https://uttam408.github.io/connector-dashboard/

## How it works

| piece | what it does |
|-------|--------------|
| `check.py` | probes each source locally, writes **sanitized** `docs/status.json` |
| `run.sh` | runs `check.py`, then commits & pushes `docs/` if it changed |
| `com.uttam.connector-dashboard.plist` | launchd agent &mdash; fires `run.sh` daily at **05:00** local |
| `docs/index.html` | zero-dependency text + emoji dashboard that renders `status.json` |

Two sections: **services** (MCP connectors, Tailscale, CLI e-mail, health
APIs, notifications, WhatsApp) and **agents** (launchd jobs).

### The rule

An entry is **green** only if its underlying credential / data / log was
refreshed within the last **24 h** (`CUTOFF_H` in `check.py`). Otherwise
**red**. Live daemons (MCP connectors via `claude mcp list`, Tailscale via
`tailscale status`) are judged by a health check. Agents that fire less than
daily (`import-downloads-to-photos`) are green if loaded and last exited
cleanly. Two intentionally-disabled agents (`strava-friends-feed`,
`battery.plist`) are shown dimmed.

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
strava-kudos, this dashboard, plus the two disabled ones.
