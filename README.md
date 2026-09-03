# connector-dashboard

Daily red/green health check of every connector, credential store, and
launchd agent this Mac depends on &mdash; published as a static dashboard on
GitHub Pages.

**Live:** https://uttam408.github.io/connector-dashboard/

## How it works

| piece | what it does |
|-------|--------------|
| `check.py` | probes each source locally, writes **sanitized** `docs/status.json` (+ `docs/history.jsonl`) |
| `run.sh` | runs `check.py`, then commits & pushes `docs/` if it changed |
| `com.uttam.connector-dashboard.plist` | launchd agent &mdash; fires `run.sh` daily at **05:00** local |
| `docs/index.html` | zero-dependency dashboard that renders `status.json` |

### The rule

An entry is **green** only if its underlying credential / data / log was
refreshed within the last **24 h** (`CUTOFF_H` in `check.py`). Otherwise
**red**. MCP connectors are judged by a live `claude mcp list` health check.
Two intentionally-disabled agents (`strava-friends-feed`, `battery.plist`)
are shown dimmed and excluded from the score.

### What is published

Only: group name, item label, colour, a short generic note, and a rounded
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

Claude.ai MCP connectors (Drive, Calendar, Gmail, PitchBook, Playwright) &middot;
`gws` CLI e-mail accounts (personal / Wharton / secondary) &middot;
Whoop (official + internal), Strava, Garmin tokens &middot;
ntfy + iMessage delivery &middot; WhatsApp local DB freshness &middot;
launchd agents (morning-checkin, checkin-digest, import-downloads-to-photos,
strava-kudos, this dashboard).
