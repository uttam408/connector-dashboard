# Status format

The dashboard at <https://uttam408.github.io/connector-dashboard/> assembles
itself **client-side** from the files in `docs/status.d/`. No server, no
assembler, no dependency on any single machine.

## One file per row

```
docs/status.d/<slug>.jsonl   a run log — for anything that runs on a schedule
docs/status.d/<slug>.json    a static row — for things that never "run"
```

`<slug>` = the label lowercased, non-alphanumerics collapsed to `-`
(`Whoop (official API)` → `whoop-official-api`, `strava-kudos-muse` →
`strava-kudos-muse`). You only ever touch your own file.

## Run log (`.jsonl`) — the common case

Newline-delimited JSON. **Line 1 is a header. Every line after it is a run.**

```
{"label":"strava-kudos-muse","section":"agents","order":45,"schedule":"MON,THU 20:00","stale_hours":30}
{"ts":"2026-09-10T04:00:12-04:00","color":"green","update":"gave 2 kudos"}
{"ts":"2026-09-10T14:20:03-04:00","color":"red","update":"session expired — re-login"}
```

**Header** (identified by having `label`):

| field | req | meaning |
|-------|-----|---------|
| `label` | yes | display name |
| `section` | yes | `"services"` or `"agents"` |
| `order` | no | sort key within the section; default `500` |
| `source` | no | which system reports this row — `"claude"` or `"muse"`. Shown as a small logo between the strip and the label. If omitted, the page infers it from the label (`*-muse` → Muse, else Claude) — but set it explicitly; don't rely on the naming heuristic. |
| `schedule` | no | recurrence — `"DAILY 06:00"` or `"MON,THU 23:00"` (days = `DAILY` or comma list of `MON..SUN`; times = comma list of 24h `HH:MM`). **The page computes the concrete next run from this live**, every render and every 30s tick — `"tonight 11 PM"`, `"tomorrow 6 AM"` — so it can never go stale the way a string frozen at report time would (e.g. still reading "tomorrow" after midnight has passed). Use this over a literal `next` whenever the row runs on a real recurrence. |
| `stale_hours` | no | if the newest run's `ts` is older than this, the page shows the row red regardless of its colour — catches an agent that silently stopped |

**Run line** (identified by having `ts`):

| field | req | meaning |
|-------|-----|---------|
| `ts` | yes | ISO-8601 **with offset**, e.g. `2026-09-10T04:00:12-04:00` |
| `color` | yes | `green` ok · `red` failed · `gray` skipped (a less-than-daily job on an off day) |
| `update` | no | what happened this run — short: `"digest sent"`, `"gave 2 kudos"` |
| `next` | no | a **literal** next-run string, for a one-off or irregular row with no real `schedule`. Frozen at write time — prefer `schedule` on the header when the recurrence is regular. |

The page shows the note as the newest run's present fields joined by ` | `:
`gave 2 kudos | 3h ago | next Sat 6:35 PM` (agents show the `ts` as "x ago";
services don't — their `update` text already carries any age that matters).
The 5-day strip is the last colour recorded on each of the last 5 calendar
days.

### Writing to it — just append

```
echo '{"ts":"'"$(date -Iseconds)"'","color":"green","update":"gave 2 kudos"}' \
  >> docs/status.d/strava-kudos-muse.jsonl
git add docs/status.d/strava-kudos-muse.jsonl
git commit -m "status: strava-kudos-muse — gave 2 kudos"
git pull --rebase && git push
```

(`schedule` on the header only needs setting/updating when the recurrence
itself changes — not on every run.)

No read, no trim, no SHA. `.gitattributes` sets `*.jsonl merge=union`, so two
agents appending at the same time auto-merge. **Trimming is central** —
`check.py` keeps the last 60 run lines per file on its 5am pass; you never
trim your own file.

If you have no working tree (pure GitHub API): GET the file for its blob SHA
+ content, add your line, PUT it back. Retry on 409.

Machines with the repo can use `report.py`:
`python3 report.py --label X --section agents --color green --update "…" --schedule "MON,THU 23:00" --source muse --push`

`--source` defaults to `claude`; Muse should always pass `--source muse` (or
set `"source":"muse"` directly when writing via the API).

`schedule.py` in the repo root exposes `next_run(spec)` — the Python twin of
the JS `nextRun()` in `docs/index.html`. Both must agree on the grammar; if
you change one, change the other.

## Static row (`.json`)

For rows that never run — paused, disabled, not-built, not-in-use:

```json
{ "label": "checkin-digest", "section": "agents", "color": "red",
  "update": "paused", "order": 20, "intentional": true }
```

`intentional: true` → dimmed, excluded from the ok/failed counts, sunk to the
bottom of its section.

## Sanitization

These files are public. **Never** put e-mail addresses, file paths, tokens,
ntfy topics, contact names, or message/digest content in any field. `update`
is a status, not a payload — "digest sent", not the digest.

## Adding a new row

Just create the file. The page lists `docs/status.d/` via the GitHub API, so
it appears on the next page load with nothing else changed anywhere.
