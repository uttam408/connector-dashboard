# Shared context

Coordination log for every agent that touches this repo (Claude sessions,
Muse cloud crons, anything else). Read the last few entries before you make
structural changes.

**Keep entries short.** Two or three lines: what changed, what other agents
must do differently, date. Newest on top. Move detail into the doc it belongs
in (`docs/STATUS-FORMAT.md`, `README.md`) and link it.

---

### 2026-09-11 — schedule goes on the header; the page computes `next` live

A `next` string computed at report time goes stale (e.g. still says
"tomorrow 6 AM" after midnight has passed). Fixed: put `"schedule":"DAILY
06:00"` / `"MON,THU 23:00"` on the header instead — the page recomputes the
concrete next run every render/tick, like it already does for "x ago". Use a
literal `next` on a run line only for one-off/irregular rows with no real
schedule. `report.py --schedule "…" --push` sets it. Details in
`docs/STATUS-FORMAT.md`.

### 2026-09-10 — `next` is a concrete instance, not a recurrence

(Superseded by the entry above — kept for history.) Put the actual next run
in `next`, not the pattern ("Mon & Thu 23:00").

### 2026-09-10 — status rows are now append-only run logs

`docs/status.d/<slug>.jsonl`: header line, then one appended line per run
`{ts, color, update?, next?}`. **Muse agents: switch from editing
`status.json` to appending to your own `.jsonl`** — spec in
`docs/STATUS-FORMAT.md`. `status.json` is a dead tombstone. `history.json`
and the pending history GitHub Action are gone (the strip is derived from the
logs; `check.py` trims them at 5am).

### 2026-09-10 — dashboard assembles client-side from per-row fragments

Page lists `docs/status.d/` via the GitHub API and renders in the browser.
No more `check.py` building one `status.json`. `check.py` only writes the
Mac-local rows now.
