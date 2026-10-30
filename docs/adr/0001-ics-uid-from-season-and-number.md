# ADR-1 — ICS UID is `npl-<year>-m<NN>@codila125.github.io`

- Status: accepted
- Date: 2026 (build time)

## Context

RFC 5545 requires a persistent, unique `UID` for each event; calendar apps that
subscribe to a feed key their local copies on the `UID`. The source offers a
UUID (`id`), a Mongo `externalId`, and a human `matchNumber`. Source ids are not
documented as stable; if the site admin re-seeds fixtures, UUID-based UIDs
would turn every event into a delete + create, producing visible duplicates and
flicker for subscribers. Playoff matches have no numeric label of their own.

## Decision

The `UID` is built only from the season year and our deterministic `number`
(1..28 league, 29..32 playoffs):

```
npl-<year>-m<NN>@codila125.github.io     # NN = number zero-padded to 2
```

Examples: `npl-2026-m07@codila125.github.io`, `npl-2026-m32@codila125.github.io`.
The same `UID` appears in `npl.ics` and in every team feed. The source UUID is
kept in `site/data/npl.json` for diagnostics only, never in the calendar.

## Consequences

- Events survive source re-seeding and reschedules; subscribers update in place
  rather than seeing delete + create churn.
- A `UID` can never be reassigned without creating duplicates for all existing
  subscribers (hard to reverse — therefore recorded).
- If the league ever renumbers matches, events change content under the same
  `UID` (calendars update in place), which is acceptable.
- Next season gets a distinct `npl-<year>-…` space.
