# Status fragment format

The dashboard at <https://uttam408.github.io/connector-dashboard/> is assembled
**client-side** from one small JSON file per row. There is no server, no
assembler, and no dependency on any single machine. Each agent writes its own
fragment whenever it runs; the page reads all of them and renders.

## Where

```
docs/status.d/<slug>.json
```

`<slug>` = the label lowercased with every run of non-alphanumerics collapsed to
`-` (e.g. label `Whoop (official API)` → `whoop-official-api.json`,
`strava-kudos-muse` → `strava-kudos-muse.json`). One file, one row. You only
ever write your own file, so there are no merge conflicts between agents.

## Schema

```json
{
  "label":   "strava-kudos-muse",
  "section": "agents",
  "color":   "green",
  "update":  "gave 2 kudos",
  "ts":      "2026-09-10T18:35:00-04:00",
  "next":    "Sat 6:35 PM",
  "order":   50,
  "intentional": false,
  "stale_hours": 26
}
```

| field | required | meaning |
|-------|----------|---------|
| `label` | yes | display name, exactly as shown on the dashboard |
| `section` | yes | `"services"` or `"agents"` |
| `color` | yes | `"green"` ok · `"red"` failed / needs attention · `"gray"` skipped (a less-than-daily job on a day it isn't scheduled) |
| `update` | no | what happened this run — short, e.g. `"digest sent"`, `"gave 2 kudos"`, `"session expired — re-login"` |
| `ts` | no | ISO-8601 timestamp of this run **with offset**. The dashboard renders it as a live "x ago" that re-ticks in the browser. |
| `next` | no | human string for the next scheduled run, e.g. `"Sat 6:35 PM"`, `"6 AM"`, `"Mon & Thu 23:00"` |
| `order` | no | sort key within the section (ascending); default `500` |
| `intentional` | no | `true` = dimmed, excluded from the green/red counts, sunk to the bottom (paused / disabled / not-in-use rows) |
| `stale_hours` | no | if set and `now - ts` exceeds it, the page shows the row red regardless of `color` — catches an agent that silently stopped running |

The dashboard composes the note line as the present fields joined by ` | `:

```
gave 2 kudos | 3h ago | next Sat 6:35 PM
```

Omit fields you don't have. A bare `{label, section, color}` is valid (that's
what most `services` rows are).

## Sanitization

Fragments are published to a public repo. **Never** put e-mail addresses, file
paths, auth tokens, ntfy topics, contact names, or message/digest content in any
field. `update` is a status, not a payload — "digest sent", not the digest.

## How to write it

- **From a machine with the repo checked out** (Mac launchd agents): use
  `report.py` in the repo root —
  `python3 report.py --label "X" --section agents --color green --update "…" --next "…" --push`
  It writes the fragment, commits just that file, and pushes with retry.
- **From the cloud / no working tree** (Muse crons, GitHub Actions): PUT the file
  via the GitHub Contents API. One file, its own blob SHA — no merge, safe to do
  concurrently with any other agent.

## History strip

`docs/history.json` (`{ "YYYY-MM-DD": { label: color } }`) is an accumulator. A
GitHub Actions cron (00:07 UTC) snapshots every current fragment's colour into
it once a day — workflow in `history-workflow.yml.pending`, to be installed at
`.github/workflows/history.yml`. The page folds the last 5 days into the strip
of squares on each row. Agents do **not** write history.json.

## Adding a new agent

Just write your fragment. The page lists `docs/status.d/` via the GitHub API, so
a new file appears on the next page load with no other change anywhere.
