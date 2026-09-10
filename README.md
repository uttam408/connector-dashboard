# connector-dashboard

Red/green health of every connector, credential store, and scheduled agent
across this Mac and the cloud &mdash; a static dashboard on GitHub Pages that
**assembles itself in the browser** from one small file per row. No server,
no assembler, no dependency on any single machine.

**Live:** https://uttam408.github.io/connector-dashboard/

## Architecture

```
docs/status.d/<slug>.json   one file per row — each agent writes its own
docs/history.json           daily colour snapshot, for the 5-day strip
docs/index.html             fetches all of the above and renders, client-side
```

- **Every row is a fragment.** An agent writes `docs/status.d/<label>.json`
  whenever it runs. The page lists the directory via the GitHub API, fetches
  each fragment, and renders. See **[docs/STATUS-FORMAT.md](docs/STATUS-FORMAT.md)**
  for the schema — this is the contract other agents (Muse cloud crons, etc.)
  write to.
- **Realtime.** A row updates the moment its agent finishes, not at 5am. The
  page re-fetches every 2 min and re-ticks the "x ago" every 30s.
- **No Mac dependency for assembly.** If the Mac is offline, only the rows it
  owns (the ones below) go stale — correctly, since those checks can't run
  anywhere else.

| piece | what it does |
|-------|--------------|
| `check.py` | probes the **Mac-local** things (MCP connectors, Tailscale, gws creds, Whoop/Strava tokens, Garmin ping, WhatsApp DB, launchd agents that don't self-report) and writes their fragments |
| `report.py` | fragment writer for machines with the repo checked out: writes one fragment, commits just that file, pushes with rebase-retry |
| `run.sh` | launchd wrapper — runs `check.py`, commits changed fragments, pushes |
| `com.uttam.connector-dashboard.plist` | launchd agent — fires `run.sh` daily at **05:00** local |
| `history-workflow.yml.pending` | GitHub Actions cron (00:07 UTC) that folds every fragment's colour into `history.json`. **Not yet installed** — move it to `.github/workflows/history.yml` and commit with a `workflow`-scoped token (`gh auth refresh -h github.com -s workflow`). |

## Colour rules

- **green** ok · **red** failed / needs attention · **gray** (💤) skipped — a
  less-than-daily agent on a day it isn't scheduled (excluded from the counts)
- **intentional** rows (paused / disabled / not-in-use) are dimmed, excluded
  from the counts, and sink to the bottom
- `stale_hours` on a fragment: the page shows it red if `now - ts` exceeds it,
  catching an agent that silently stopped

Where `check.py` still judges freshness itself:
- **gws CLI creds / Whoop / Strava tokens** — file mtime within 24h
- **Garmin** — a real ~1s `garminconnect` ping (on-demand CLI; file age is
  meaningless because the library silently refreshes an expired token)
- **Whoop internal API** — stays on the age rule; that endpoint has no refresh
  flow, so staleness genuinely means "go re-login"
- **launchd agents** — loaded + last exit code; `import-downloads-to-photos`
  (Mon & Thu) is gray on off-days

## 5-day strip

Each row leads with five squares, oldest → today. `docs/history.json`
(`{"YYYY-MM-DD": {label: colour}}`) is filled by the GitHub Action once a day;
the page folds the last five in. `⬜` = no record (row didn't exist / no
snapshot). Hover for the date and state.

## Adding / updating a row

- **Machine with the repo:** `python3 report.py --label "X" --section agents
  --color green --update "…" --next "…" --push`
- **Cloud / no checkout:** PUT `docs/status.d/<slug>.json` via the GitHub
  Contents API — one file, no merge. Schema in `docs/STATUS-FORMAT.md`.

A brand-new label appears on the next page load with no other change anywhere.

## Setup

```sh
./install.sh                                                        # load the launchd agent
launchctl kickstart -k gui/$(id -u)/com.uttam.connector-dashboard   # run now
```

GitHub Pages: **Settings → Pages → Deploy from a branch → `main` / `/docs`**.
The `history` workflow needs no setup beyond being on the default branch.

## Sanitization

Fragments are public. **Never** put e-mail addresses, file paths, tokens,
ntfy topics, contact names, or message/digest content in any field. `report.py`
rejects the obvious cases.
