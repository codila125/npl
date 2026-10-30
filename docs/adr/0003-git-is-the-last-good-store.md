# ADR-3 — Git is the last-good store: validate fully in memory, then write

- Status: accepted
- Date: 2026 (build time)

## Context

AC-6 requires that when the source is unreachable, changed shape, or returns
implausible data, the scraper exits non-zero **without overwriting the last
good data**, so the published site and feeds keep serving the previous state
and the workflow run shows as failed. The data and feeds are plain files under
`site/`, committed by the Action and deployed from that commit.

A scraper that streamed files to disk as it went would leave a half-updated
`site/` on the failure path: some new files, some old, and — worse — a
successful deploy of inconsistent data from a later run.

## Decision

- The CLI builds every output in memory: fetch/load the raw source, normalize,
  validate the normalized season (V1..V16, including the V15 regression guard
  against the committed `site/data/npl.json`), and only then write.
- Writing goes through `publish.write_outputs`: write-to-temp + `os.replace`,
  only files whose bytes differ, with orphan `calendar/*.ics` cleaned up in the
  same step.
- Any `ScrapeError` or violation exits `1` before a single file is touched.
- The workflow commits only after the scraper exits `0`, and the deploy job
  checks out the commit that contains the data. On a failed scheduled run
  nothing is committed, nothing is deployed, and the run is red.
- The regression guard may only be bypassed deliberately, via
  `--allow-regression` / the `workflow_dispatch` input.

## Consequences

- The history of `site/` doubles as an audit log of every data change; the
  rollback path is reverting a bot commit.
- The repo gains data commits during the season, bounded by real changes
  (ADR-2), not by the cron cadence.
- A legitimate "fewer completed matches" correction needs a manual run with
  `allow_regression` — a rare, deliberate and visible action.
- No separate "last good" copy or branch has to be maintained.
