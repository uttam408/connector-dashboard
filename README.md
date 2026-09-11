# connector-dashboard

Red/green health of every connector, credential store, and scheduled agent
across this Mac and the cloud &mdash; a static dashboard on GitHub Pages that
**assembles itself in the browser** from one small file per row. No server,
no assembler, no dependency on any single machine.

**Live:** https://uttam408.github.io/connector-dashboard/

## Architecture

```
docs/status.d/<slug>.jsonl  append-only run log — header line + one line per run
docs/status.d/<slug>.json   static row — for things that never "run"
docs/index.html             lists status.d/ via the GitHub API, renders client-side
SHARED-CONTEXT.md            coordination log — read it before structural changes
```

- **Every row is its own file.** An agent **appends** one line to its
  `.jsonl` whenever it runs — `{ts, color, update?, next?}`. No read, no
  merge (`.gitattributes: *.jsonl merge=union`). See
  **[docs/STATUS-FORMAT.md](docs/STATUS-FORMAT.md)** for the schema — the
  contract other agents (Muse cloud crons) write to.
- **Realtime.** A row updates the moment its agent finishes. The page
  re-fetches every 2 min and re-ticks "x ago" every 30s.
- **No Mac dependency for assembly.** The page needs only the files in
  `status.d/`. `check.py` writes the Mac-local rows and trims every log; if
  the Mac is offline those rows go stale (correct) and logs grow a little
  (harmless).

| piece | what it does |
|-------|--------------|
| `check.py` | probes the **Mac-local** things (MCP connectors, Tailscale, gws creds, Whoop/Strava tokens, Garmin ping, WhatsApp DB, launchd agents that don't self-report), appends their run lines, and trims every `*.jsonl` to the last 60 runs |
| `report.py` | appender for machines with the repo checked out: adds one run line, commits just that file, pushes with rebase-retry |
| `run.sh` | launchd wrapper — runs `check.py`, commits, pushes |
| `com.uttam.connector-dashboard.plist` | launchd agent — fires `run.sh` daily at **05:00** local |

## Colour rules

- **green** ok · **red** failed / needs attention · **gray** (💤) skipped — a
  less-than-daily agent on a day it isn't scheduled (excluded from the counts)
- **intentional** rows (paused / disabled / not-in-use) are dimmed, excluded
  from the counts, and sink to the bottom
- `stale_hours` in a log's header: the page shows the row red if the newest
  run's `ts` is older than it — catches an agent that silently stopped

Where `check.py` still judges freshness itself:
- **gws CLI creds / Whoop / Strava tokens** — file mtime within 24h
- **Garmin** — a real ~1s `garminconnect` ping (on-demand CLI; file age is
  meaningless because the library silently refreshes an expired token)
- **Whoop internal API** — stays on the age rule; that endpoint has no refresh
  flow, so staleness genuinely means "go re-login"
- **launchd agents** — loaded + last exit code; `downloads-to-photos`
  (Mon & Thu) is gray on off-days, with the last run's import count as its
  update text

## 5-day strip

Each row leads with five squares, oldest → today: the last colour recorded on
each of the last 5 calendar days, read straight from the `.jsonl`. `⬜` = no
run logged that day. Hover for the date and state.

## Adding / updating a row

- **Machine with the repo:** `python3 report.py --label "X" --section agents
  --color green --update "…" --next "…" --push` — or just append a line and
  `git commit && git pull --rebase && git push`.
- **Cloud / no checkout:** GET the `.jsonl` for its blob SHA + content, add
  your line, PUT it back (retry on 409). Schema in `docs/STATUS-FORMAT.md`.

A brand-new label appears on the next page load with no other change anywhere.

## Setup

```sh
./install.sh                                                        # load the launchd agent
launchctl kickstart -k gui/$(id -u)/com.uttam.connector-dashboard   # run now
```

GitHub Pages: **Settings → Pages → Deploy from a branch → `main` / `/docs`**.

## Sanitization

Fragments are public. **Never** put e-mail addresses, file paths, tokens,
ntfy topics, contact names, or message/digest content in any field. `report.py`
rejects the obvious cases.
