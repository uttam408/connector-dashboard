# Shared context

Coordination log for every agent that touches this repo (Claude sessions,
Muse cloud crons, anything else). Read the last few entries before you make
structural changes.

**Keep entries short.** Two or three lines: what changed, what other agents
must do differently, date. Newest on top. Move detail into the doc it belongs
in (`docs/STATUS-FORMAT.md`, `README.md`) and link it.

---

### 2026-09-11 — WRTCbot: moved to Wed noon; check.py marks its off-days gray

Member-email draft moved Thu 8am -> Wed **noon** (local launchd plist).
Coffee-sync draft stays Fri 5pm (cloud routine). Neither self-reporter
touches Mon/Tue/Thu/Sat/Sun, so `check.py`'s 5am pass now appends a gray
"not scheduled today" line on those five days only — never on Wed/Fri,
where the real self-report (more accurate than a generic heuristic) wins.
Also: the `wrtcbot.json` static stub was STILL live in the repo until just
now — `report.py --push` only `git add`s the one `.jsonl` it just wrote, so
an earlier `rm wrtcbot.json` on disk never got committed. If you remove a
status file by hand outside `report.py`/`check.py`'s own git calls, commit
that deletion yourself — don't assume it's pushed.

---

### 2026-09-11 — WRTCbot collapsed back to one row for both halves

(Supersedes the entry directly below.) K'far order sync is NOT a separate
row — both halves (Thu 8am member-email draft, local launchd; Fri 5pm
K'far coffee-sync draft, cloud routine) write into the same `wrtcbot.jsonl`.
The two runs are different day+time pairs with no clean `schedule` grammar
cross-product, so the header has no `schedule` — each run instead sets a
literal `--next` pointing at the other half ("Thu 8 AM (email)" / "Fri 5 PM
(coffee)"). `stale_hours: 170` covers the longer Fri→Thu gap.

### 2026-09-11 — WRTCbot is real now; added K'far order sync row

`wrtcbot.json` stub ("not built yet") replaced with `wrtcbot.jsonl` — the
WRTC weekly run-announcement email now actually drafts (local launchd, Thu
8am; `~/.claude/skills/wrtc-coffee-email/scripts/weekly_draft.js` self-reports
via `report.py`). Added new row `k-far-order-sync.jsonl` for the separate
Friday 5pm K'far beverage-order draft, which runs as a claude.ai cloud
routine (`trig_019pCRFsZRE7RLCvfmgYroWN`, sources this repo, self-reports at
the end of its own prompt). Both only ever *draft* — color reflects whether
the draft was built, not whether a human has sent it yet.

---

### 2026-09-11 — downloads-to-photos row: renamed + shows real last-run counts

`import-downloads-to-photos.jsonl` renamed to `downloads-to-photos.jsonl`
(label + slug only — the underlying launchd label/log path are unchanged).
`check.py`'s `check_agent` now parses the log's last "Done. Imported: N,
Failed: M." line for the update text on off-days too, instead of always
writing "not scheduled today" — the row shows what actually happened last
time (e.g. "5 imported").

### 2026-09-11 — leftover test dupes in two rows from the schedule-header work

`import-downloads-to-photos.jsonl` and `morning-checkin.jsonl` each had 5-6
duplicate synthetic run lines (literal `next` values like "6 AM" / "tomorrow
6 AM") left over from testing the fix below — never real runs, since current
`check.py` doesn't emit `next` for either. Trimmed `import-downloads-to-photos`
back to real backfill + one real check_agent line. `morning-checkin` still has
its dupes — owner should trim it back to its last real backfill line the same
way.

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
