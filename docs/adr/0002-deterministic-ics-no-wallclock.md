# ADR-2 — `.ics` is a pure function of `npl.json`; no wall clock

- Status: accepted
- Date: 2026 (build time)

## Context

The cron runs every 30 minutes. A `DTSTAMP`/`updated_at` of "now" would change
every file on every run, producing ~48 meaningless commits/day, a noisy
history, and a Pages redeploy each time. RFC 5545 only requires `DTSTAMP` to be
a UTC time of creation/revision of the iCalendar object.

## Decision

- `updated_at` = max source `updatedAt`.
- Per-event `DTSTAMP`/`LAST-MODIFIED` = that match's source `updatedAt`
  (falling back to the season `updated_at` only when the match has none).
- The generator (`scraper/ics.py`) takes only the data dict and never reads a
  clock (`datetime.now`/`utcnow`/`time.time` are banned; a test greps for them).
- The publisher writes a file only when its bytes differ.

## Consequences

- Re-runs on unchanged source produce zero diff, so commits happen only on real
  change.
- "Last updated" in the UI means "when the source last changed", not "when we
  last checked" (the footer says "refreshed about every 30 minutes").
- Two builds from the same `npl.json` are byte-identical.
- If the source ever bumps `updatedAt` spuriously, we would get extra commits
  but never incorrect data.
