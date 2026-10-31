# npl

Standings, match schedule and calendar feeds for the **Nepal Premier League 2026 (Season 3)**,
26 Oct – 21 Nov 2026 at TU Ground, Kirtipur.

- Site: <https://codila125.github.io/npl/>
- All matches calendar feed: <https://codila125.github.io/npl/calendar/npl.ics>
- Per-team feeds: `https://codila125.github.io/npl/calendar/<team-slug>.ics` (one per franchise,
  e.g. [`lumbini-lions.ics`](https://codila125.github.io/npl/calendar/lumbini-lions.ics))

A scheduled GitHub Action scrapes the official source every 30 minutes, rebuilds
`site/data/npl.json` and the `.ics` feeds, commits them only when they changed, and deploys the
`site/` folder to GitHub Pages. Nobody has to run anything.

Unofficial fan project. Data from [nplt20league.com](https://nplt20league.com/).

## How it works

```
scraper/            Python 3.12 scraper + generator (stdlib + requests)
  fetch.py          robots.txt check, GetJSON with UA/timeout/retry, offline loader
  normalize.py      raw source dicts -> normalized Season dict (pure)
  validate.py       V1..V16 rules; any violation fails the run (pure)
  ics.py            Season dict -> calendar/npl.ics + one feed per team (pure, no clock)
  publish.py        render npl.json, write-only-if-changed, orphan cleanup
  cli.py            `python -m scraper` orchestration, exit codes
site/               exactly what GitHub Pages serves (the artifact)
  index.html style.css app.js
  data/npl.json     normalized data the page reads (committed by the bot)
  calendar/*.ics    all-matches + per-team feeds (committed by the bot)
worker/live.js      Cloudflare Worker: CORS proxy for live scores (see "Live scores")
tests/              offline tests (fixtures copied from saved source responses)
docs/adr/           decisions: ICS UID, determinism, git-as-last-good-store
```

The page is plain HTML/CSS/vanilla JS with no build step. The feeds are a pure function of
`site/data/npl.json`, so an unchanged source produces a zero-byte diff and no commit.

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# scrape the live source, rewrite site/ only where bytes differ
.venv/bin/python -m scraper

# rebuild from saved source files instead of the network (dev / tests / seed)
.venv/bin/python -m scraper --from-dir tests/fixtures/season2026

# see what would change without writing anything
.venv/bin/python -m scraper --dry-run

# allow fewer completed matches than the committed data (rule V15)
.venv/bin/python -m scraper --allow-regression
```

Preview the site locally:

```sh
cd site && python3 -m http.server 8000   # http://localhost:8000/
```

## Gates

| Gate | Command |
|------|---------|
| `lint` | `ruff check .` |
| `test` | `python -m pytest -q` |

There is no typecheck and no build step (the site is static files). CI runs both gates on every
push and pull request (`.github/workflows/ci.yml`). The tests are fully offline: network access
lives behind an injected session in `scraper/fetch.py` and the parsing tests use saved source
snapshots under `tests/fixtures/`.

## Data source

Official NPL API, four requests per run, sequential, identified with
`npl-calendar-bot/1.0 (+https://github.com/codila125/npl)`:

- `GET https://nplt20league.com/robots.txt` (checked; a disallow fails the run)
- `GET https://nplt20league.com/api/v1/teams`
- `GET https://nplt20league.com/api/v1/matches?season=2026`
- `GET https://nplt20league.com/api/v1/points?season=2026`
- `GET https://nplt20league.com/api/v1/stats?season=2026` (optional: leaderboards for the Stats
  section; if it fails or does not validate (rule V17) the run keeps the last published stats)

Start times come from `matches[].playedAt` and are cross-checked against the source's
`timeLabel`/`dateLabel` (rule V9); a mismatch fails the run rather than publishing wrong times.
`fixtures` is deliberately not fetched — `matches` already carries scheduled and played matches.

**Fallbacks (manual only).** If the official API disappears or changes shape, the run turns red
and the site keeps the last good data while someone re-points the scraper. The documented escape
hatches are the ESPNcricinfo public JSON for the NPL series and the Wikipedia season article; both
would need a small adapter in `scraper/normalize.py` and an updated `SOURCE_BASE` in
`scraper/config.py`. Do **not** lower validation rules to make a broken source pass — write the
adapter instead.

## Live scores

The published data only refreshes every ~30 minutes, and the official API rejects browser
requests from other origins, so live scores go through a tiny Cloudflare Worker
(`worker/live.js`). It fetches the same `matches` endpoint with the same User-Agent, keeps the
result for 30 s per isolate, trims it to status/result/score/overs/target per match, and serves it
with CORS for `https://codila125.github.io` (and `http://localhost:8000` for local preview).

The page polls it every 30 s, only while the tab is visible and only from 15 minutes before a
match's start until it is completed in the published data (capped at 6 hours). The panel shows
exactly what the source reports; when the source has no score yet it says so rather than
guessing. If the Worker is down the panel says so and the rest of the page is unaffected.

Deploy (once, from a Cloudflare account):

```sh
cd worker && npx wrangler login && npx wrangler deploy
```

Then set `LIVE_URL` at the top of `site/app.js` to the printed URL plus `/live`
(e.g. `https://npl-live.<subdomain>.workers.dev/live`). An empty `LIVE_URL` disables the panel.

## Failure behaviour

The scraper validates everything in memory first (HTTP status, JSON shape, season/year, 8 teams,
32 matches with the expected stage counts, labels, participants, start times, venues, winners,
standings, regression against the committed data). Any violation prints
`error: [V<n>] <message>` (plus `::error::` annotations on GitHub Actions), exits `1`, and touches
no file. The workflow then makes no commit and, for scheduled runs, no deploy — so the published
site and the feeds keep the previous data and the run shows as failed.

## Scheduled workflow

`.github/workflows/scrape.yml` runs on:

- `cron: "7,37 * * * *"` — every 30 minutes,
- `workflow_dispatch` (with an optional `allow_regression` input),
- pushes to `main` (so code and site changes also reach Pages).

The `scrape` job has `contents: write` and commits `site/` only when it changed; the `deploy` job
publishes that commit to Pages and only runs on schedule when the data changed. GitHub emails the
repo owner when a scheduled run fails.

**If the cron stops firing:** GitHub disables scheduled workflows after ~60 days without repo
activity. Re-enable it in the Actions tab (select the workflow → *Enable workflow*), or push any
commit. Then run the workflow once with *Run workflow* (`workflow_dispatch`) to refresh and
redeploy.

## License

Data © Nepal Premier League / its provider. This repository's code is provided as-is for the fan
site above.
