"""V3..V16 validation of a normalized Season against its raw source.

Signature (see ``config.py`` for the constants used)::

    validate(raw, season, previous=None, allow_regression=False) -> list[Violation]

``raw`` is a ``RawSource`` (the fetched/loaded source). It is needed for the
rules that inspect source-only fields the normalized JSON does not keep:
V3 (year), V4 (teams), V5/V6 (matches), V7/V8 (participants), V9
(playedAt/timeLabel/dateLabel), V10 (venueLabel), V11 (winnerTeamId),
V12 (standings), V13 (updatedAt). ``season`` is the normalized dict and backs
V14/V15/V16.

Callers normalize *before* calling validate: rules V9 and V13 read raw fields
that ``normalize()`` itself would reject, so the raw source given to
``normalize()`` must be parseable even when those rules will flag it.

Returns every violation, never just the first. Any violation means the run must
fail and write nothing (ADR-3).
"""

import re
from datetime import datetime

from . import config
from .errors import Violation
from .normalize import RawSource

SLUG_RE = re.compile(r"^[a-z0-9-]+$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_TEXT_LEN = 200

_STAGE_COUNTS = {
    "league": 28,
    "qualifier_1": 1,
    "eliminator": 1,
    "qualifier_2": 1,
    "final": 1,
}


def _parse_dt(value) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def validate(
    raw: RawSource, season: dict, previous: dict | None = None, allow_regression: bool = False
) -> list[Violation]:
    violations: list[Violation] = []
    violations += _v3_season_year(raw)
    violations += _v4_teams(raw)
    violations += _v5_matches(raw)
    violations += _v6_league_labels(raw)
    violations += _v7_league_participants(raw)
    violations += _v8_nonleague_participants(raw)
    violations += _v9_start_times(raw)
    violations += _v10_venues(raw)
    violations += _v11_winners(raw)
    violations += _v12_standings(raw)
    violations += _v13_updated_at(raw)
    violations += _v14_output_sanity(season)
    violations += _v15_regression(season, previous, allow_regression)
    violations += _v16_strings(season)
    return violations


def _v3_season_year(raw: RawSource) -> list[Violation]:
    out = []
    for m in raw.matches:
        if m.get("year") != config.SEASON_YEAR:
            out.append(
                Violation(
                    "V3", f"{m.get('matchNumber')} year {m.get('year')!r} != {config.SEASON_YEAR}"
                )
            )
    for p in raw.points:
        if p.get("year") != config.SEASON_YEAR:
            out.append(
                Violation(
                    "V3",
                    f"points {p.get('position')} year {p.get('year')!r} != {config.SEASON_YEAR}",
                )
            )
    return out


def _v4_teams(raw: RawSource) -> list[Violation]:
    teams = raw.teams
    out = []
    if len(teams) != config.EXPECTED_TEAMS:
        out.append(Violation("V4", f"expected {config.EXPECTED_TEAMS} teams, got {len(teams)}"))
    ids = [t.get("id") for t in teams]
    if len(set(ids)) != len(ids):
        out.append(Violation("V4", "duplicate team ids"))
    slugs = [t.get("slug") for t in teams]
    if len(set(slugs)) != len(slugs):
        out.append(Violation("V4", "duplicate team slugs"))
    for t in teams:
        slug = t.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            out.append(Violation("V4", f"team slug {slug!r} does not match ^[a-z0-9-]+$"))
        elif slug == "npl":
            out.append(Violation("V4", "team slug must not be 'npl'"))
        if not t.get("name") or not str(t["name"]).strip():
            out.append(Violation("V4", f"team {slug!r} has an empty name"))
        if not t.get("shortCode") or not str(t["shortCode"]).strip():
            out.append(Violation("V4", f"team {slug!r} has an empty shortCode"))
    return out


def _v5_matches(raw: RawSource) -> list[Violation]:
    matches = raw.matches
    out = []
    if len(matches) != config.EXPECTED_MATCHES:
        out.append(
            Violation("V5", f"expected {config.EXPECTED_MATCHES} matches, got {len(matches)}")
        )
    counts: dict = {}
    for m in matches:
        stage = m.get("stage")
        counts[stage] = counts.get(stage, 0) + 1
    for stage, expected in _STAGE_COUNTS.items():
        if counts.get(stage) != expected:
            out.append(
                Violation(
                    "V5", f"stage {stage} has {counts.get(stage, 0)} matches, expected {expected}"
                )
            )
    for stage in counts:
        if stage not in _STAGE_COUNTS:
            out.append(Violation("V5", f"unknown stage {stage!r}"))
    ids = [m.get("id") for m in matches]
    if len(set(ids)) != len(ids):
        out.append(Violation("V5", "duplicate match ids"))
    return out


def _v6_league_labels(raw: RawSource) -> list[Violation]:
    labels = sorted(
        (str(m.get("matchNumber")) for m in raw.matches if m.get("stage") == "league"),
        key=lambda s: (len(s), s),
    )
    expected = [f"Match {i}" for i in range(1, 29)]
    if labels != expected:
        out = [Violation("V6", "league labels are not exactly Match 1..Match 28, once each")]
        return out
    return []


def _v7_league_participants(raw: RawSource) -> list[Violation]:
    team_ids = {t["id"] for t in raw.teams}
    slug_by_id = {t["id"]: t["slug"] for t in raw.teams}
    out = []
    for m in raw.matches:
        if m.get("stage") != "league":
            continue
        participants = m.get("participants") or []
        by_side = {p.get("side"): p for p in participants}
        team1, team2 = by_side.get("team1"), by_side.get("team2")
        if team1 is None or team2 is None or len(participants) != 2:
            out.append(
                Violation("V7", f"{m.get('matchNumber')} must have exactly team1 and team2 sides")
            )
            continue
        for label, p in (("team1", team1), ("team2", team2)):
            tid = p.get("teamId")
            if tid is None:
                out.append(Violation("V7", f"{m.get('matchNumber')} {label} has a null teamId"))
            elif tid not in team_ids:
                out.append(
                    Violation("V7", f"{m.get('matchNumber')} {label} has unknown teamId {tid!r}")
                )
            elif p.get("slug") != slug_by_id[tid]:
                out.append(
                    Violation(
                        "V7", f"{m.get('matchNumber')} {label} slug does not match the team's slug"
                    )
                )
        if team1.get("teamId") is not None and team1.get("teamId") == team2.get("teamId"):
            out.append(Violation("V7", f"{m.get('matchNumber')} has the same team on both sides"))
    return out


def _v8_nonleague_participants(raw: RawSource) -> list[Violation]:
    team_ids = {t["id"] for t in raw.teams}
    out = []
    for m in raw.matches:
        if m.get("stage") == "league":
            continue
        participants = m.get("participants") or []
        by_side = {p.get("side"): p for p in participants}
        team1, team2 = by_side.get("team1"), by_side.get("team2")
        if team1 is None or team2 is None or len(participants) != 2:
            out.append(Violation("V8", f"{m.get('matchNumber')} must have exactly two sides"))
            continue
        real_teams = []
        for label, p in (("team1", team1), ("team2", team2)):
            tid = p.get("teamId")
            if tid is None:
                continue  # placeholder side
            if tid not in team_ids:
                out.append(
                    Violation("V8", f"{m.get('matchNumber')} {label} has unknown teamId {tid!r}")
                )
            else:
                real_teams.append(tid)
        if len(real_teams) == 2 and real_teams[0] == real_teams[1]:
            out.append(
                Violation("V8", f"{m.get('matchNumber')} has the same real team on both sides")
            )
    return out


def _date_label_matches(npt: datetime, label) -> bool:
    if label is None:
        return False
    # strptime with %d requires a year on Python 3.13+; pin a dummy one.
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(f"2000 {label}", f"%Y {fmt}")
        except ValueError:
            continue
        if (parsed.month, parsed.day) == (npt.month, npt.day):
            return True
    return False


def _v9_start_times(raw: RawSource) -> list[Violation]:
    out = []
    for m in raw.matches:
        label = m.get("matchNumber")
        played = m.get("playedAt")
        try:
            dt = _parse_dt(played)
        except (ValueError, TypeError):
            out.append(Violation("V9", f"{label} has an unparsable playedAt {played!r}"))
            continue
        npt = dt.astimezone(config.NPT)
        if not (config.SEASON_WINDOW[0] <= npt.date() <= config.SEASON_WINDOW[1]):
            out.append(
                Violation("V9", f"{label} NPT date {npt.date()} is outside {config.SEASON_WINDOW}")
            )
        npt_time = npt.strftime("%I:%M %p")
        if npt_time != m.get("timeLabel"):
            out.append(
                Violation("V9", f"{label} NPT time {npt_time} != timeLabel {m.get('timeLabel')!r}")
            )
        if not _date_label_matches(npt, m.get("dateLabel")):
            out.append(
                Violation("V9", f"{label} NPT date does not match dateLabel {m.get('dateLabel')!r}")
            )
    return out


def _v10_venues(raw: RawSource) -> list[Violation]:
    out = []
    for m in raw.matches:
        venue = m.get("venueLabel")
        if not isinstance(venue, str) or not venue.strip():
            out.append(Violation("V10", f"{m.get('matchNumber')} has an empty venueLabel"))
    return out


def _v11_winners(raw: RawSource) -> list[Violation]:
    out = []
    for m in raw.matches:
        winner = m.get("winnerTeamId")
        if winner is None:
            continue
        participant_ids = [p.get("teamId") for p in (m.get("participants") or [])]
        if winner not in participant_ids:
            out.append(
                Violation("V11", f"{m.get('matchNumber')} winner {winner!r} is not a participant")
            )
    return out


def _v12_standings(raw: RawSource) -> list[Violation]:
    team_ids = {t["id"] for t in raw.teams}
    rows = raw.points
    out = []
    n = config.EXPECTED_TEAMS
    if len(rows) != n:
        out.append(Violation("V12", f"expected {n} standings rows, got {len(rows)}"))
    ids = [r.get("teamId") for r in rows]
    if len(set(ids)) != len(ids):
        out.append(Violation("V12", "duplicate teamId in standings"))
    for r in rows:
        if r.get("teamId") not in team_ids:
            out.append(
                Violation(
                    "V12",
                    f"standings row {r.get('position')} has unknown teamId {r.get('teamId')!r}",
                )
            )
    positions = [r.get("position") for r in rows]
    if positions != sorted(positions):
        out.append(Violation("V12", "standings rows are not ordered by position"))
    if sorted(positions) != list(range(1, n + 1)):
        out.append(Violation("V12", f"standings positions are not exactly 1..{n}"))
    for r in rows:
        pos = r.get("position")
        for key in ("matches", "won", "lost", "tied", "noResult", "points"):
            value = r.get(key)
            if type(value) is not int or value < 0:
                out.append(Violation("V12", f"row {pos} {key}={value!r} is not a non-negative int"))
        counts = ("matches", "won", "lost", "tied", "noResult")
        if (
            all(type(r.get(k)) is int for k in counts)
            and r["matches"] != r["won"] + r["lost"] + r["tied"] + r["noResult"]
        ):
            out.append(Violation("V12", f"row {pos} matches != won+lost+tied+noResult"))
        nrr = r.get("netRunRate")
        try:
            nrr_value = float(nrr)
        except (TypeError, ValueError):
            out.append(Violation("V12", f"row {pos} netRunRate {nrr!r} is not numeric"))
        else:
            if abs(nrr_value) >= 20:
                out.append(Violation("V12", f"row {pos} |netRunRate| >= 20"))
    return out


def _v13_updated_at(raw: RawSource) -> list[Violation]:
    out = []
    found_any = False
    for m in raw.matches:
        value = m.get("updatedAt")
        if value is None:
            continue
        found_any = True
        try:
            _parse_dt(value)
        except (ValueError, TypeError):
            out.append(
                Violation("V13", f"{m.get('matchNumber')} has an unparsable updatedAt {value!r}")
            )
    for p in raw.points:
        value = p.get("updatedAt")
        if value is None:
            continue
        found_any = True
        try:
            _parse_dt(value)
        except (ValueError, TypeError):
            out.append(
                Violation(
                    "V13", f"points row {p.get('position')} has an unparsable updatedAt {value!r}"
                )
            )
    if not found_any:
        out.append(Violation("V13", "no updatedAt present in any match or points row"))
    return out


def _v14_output_sanity(season: dict) -> list[Violation]:
    out = []
    for key in ("teams", "standings", "matches"):
        if not season.get(key):
            out.append(Violation("V14", f"normalized `{key}` is empty"))
    return out


def _v15_regression(season: dict, previous: dict | None, allow_regression: bool) -> list[Violation]:
    if previous is None or allow_regression:
        return []
    if previous.get("season", {}).get("year") != season.get("season", {}).get("year"):
        return []
    prev_completed = sum(1 for m in previous.get("matches", []) if m.get("status") == "completed")
    new_completed = sum(1 for m in season.get("matches", []) if m.get("status") == "completed")
    if new_completed < prev_completed:
        return [
            Violation(
                "V15", f"completed matches regressed from {prev_completed} to {new_completed}"
            )
        ]
    return []


def _check_text(value, where: str, out: list[Violation]) -> None:
    if value is None:
        return
    if CONTROL_RE.search(str(value)):
        out.append(Violation("V16", f"{where} contains a control character"))
    if len(str(value)) > MAX_TEXT_LEN:
        out.append(Violation("V16", f"{where} is longer than {MAX_TEXT_LEN} characters"))


def _v16_strings(season: dict) -> list[Violation]:
    out = []
    for team in season.get("teams", []):
        _check_text(team.get("name"), f"team {team.get('slug')!r} name", out)
        _check_text(team.get("short"), f"team {team.get('slug')!r} short", out)
    for m in season.get("matches", []):
        _check_text(m.get("venue"), f"match {m.get('number')} venue", out)
        _check_text(m.get("result"), f"match {m.get('number')} result", out)
        for i, side in enumerate(m.get("teams", [])):
            _check_text(side.get("name"), f"match {m.get('number')} side {i} name", out)
            _check_text(side.get("short"), f"match {m.get('number')} side {i} short", out)
    return out
