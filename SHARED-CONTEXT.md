# Shared context

Coordination log for every agent that touches this repo (Claude sessions,
Muse cloud crons, anything else). Read the last few entries before you make
structural changes.

**Keep entries short.** Two or three lines: what changed, what other agents
must do differently, date. Newest on top. Move detail into the doc it belongs
in (`docs/STATUS-FORMAT.md`, `README.md`) and link it.

---

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
