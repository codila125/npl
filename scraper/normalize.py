"""Raw source dicts -> normalized Season dict (pure)."""

import re
from datetime import UTC, datetime
from typing import NamedTuple

from . import config

PLAYOFF_NUMBERS = {"qualifier_1": 29, "eliminator": 30, "qualifier_2": 31, "final": 32}


class RawSource(NamedTuple):
    teams: list
    matches: list
    points: list


def _number(raw_match: dict) -> int:
    stage = raw_match["stage"]
    if stage in PLAYOFF_NUMBERS:
        return PLAYOFF_NUMBERS[stage]
    return int(raw_match["matchNumber"].removeprefix("Match "))


PLACEHOLDERS = {
    "qualifier_1": ("1st place", "2nd place"),
    "eliminator": ("3rd place", "4th place"),
    "qualifier_2": ("Loser of Qualifier 1", "Winner of Eliminator"),
    "final": ("Winner of Qualifier 1", "Winner of Qualifier 2"),
}


def _side(participant: dict, placeholder_name: str | None) -> dict:
    if participant["teamId"] is None:
        return {
            "slug": None,
            "name": placeholder_name or participant.get("teamName") or "TBA",
            "short": None,
            "placeholder": True,
            "score": None,
            "overs": None,
        }
    return {
        "slug": participant["slug"],
        "name": participant["teamName"],
        "short": participant["shortCode"],
        "placeholder": False,
        "score": participant.get("score"),
        "overs": participant.get("overs"),
    }


def _sides(m: dict) -> list[dict]:
    by_side = {p["side"]: p for p in m["participants"]}
    names = PLACEHOLDERS.get(m["stage"], (None, None))
    return [_side(by_side["team1"], names[0]), _side(by_side["team2"], names[1])]


NO_RESULT_RE = re.compile(
    r"no result|abandon|washed|called off|cancel|without a ball", re.IGNORECASE
)


def _text(value: str | None) -> str | None:
    """Verbatim string, with blank/whitespace-only collapsed to None."""
    return value if value is not None and value.strip() else None


def _status(raw_status: str) -> str:
    if raw_status in ("scheduled", "start_in"):
        return "scheduled"
    if raw_status == "completed":
        return "completed"
    return "other"


def _outcome(status: str, result: str | None, winner: str | None) -> str | None:
    if status != "completed":
        return None
    if winner is None and (result is None or NO_RESULT_RE.search(result)):
        return "no_result"
    return "result"


def _utc(value: str) -> str:
    """ISO-8601 (Z or offset) -> `YYYY-MM-DDTHH:MM:SSZ`."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _match(m: dict, slug_by_team_id: dict[str, str], season_updated_at: str) -> dict:
    status = _status(m["status"])
    result = _text(m.get("result"))
    winner = slug_by_team_id.get(m.get("winnerTeamId"))
    return {
        "number": _number(m),
        "label": m["matchNumber"],
        "stage": m["stage"],
        "id": m["id"],
        "start_utc": _utc(m["playedAt"]),
        "venue": m["venueLabel"],
        "status": status,
        "status_raw": m["status"],
        "teams": _sides(m),
        "result": result,
        "outcome": _outcome(status, result, winner),
        "winner": winner,
        "updated_at": _utc(m["updatedAt"]) if m.get("updatedAt") else season_updated_at,
    }


def _team(t: dict) -> dict:
    return {"slug": t["slug"], "name": t["name"], "short": t["shortCode"]}


def _standing(p: dict, slug_by_team_id: dict[str, str]) -> dict:
    return {
        "position": p["position"],
        "team": slug_by_team_id[p["teamId"]],
        "played": p["matches"],
        "won": p["won"],
        "lost": p["lost"],
        "tied": p["tied"],
        "no_result": p["noResult"],
        "points": p["points"],
        "nrr": float(p["netRunRate"]),
    }


def normalize(raw: RawSource) -> dict:
    slug_by_team_id = {t["id"]: t["slug"] for t in raw.teams}
    stamps = [_utc(r["updatedAt"]) for r in (*raw.points, *raw.matches) if r.get("updatedAt")]
    updated_at = max(stamps)
    matches = [_match(m, slug_by_team_id, updated_at) for m in raw.matches]
    return {
        "schema_version": config.SCHEMA_VERSION,
        "season": {
            "year": config.SEASON_YEAR,
            "name": config.SEASON_NAME,
            "timezone": "Asia/Kathmandu",
            "utc_offset": "+05:45",
        },
        "updated_at": updated_at,
        "source": {"name": "nplt20league.com", "url": config.SOURCE_BASE + "/"},
        "teams": sorted((_team(t) for t in raw.teams), key=lambda t: t["name"]),
        "standings": sorted(
            (_standing(p, slug_by_team_id) for p in raw.points), key=lambda r: r["position"]
        ),
        "matches": sorted(matches, key=lambda m: (m["start_utc"], m["number"])),
    }
