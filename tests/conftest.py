import json
from pathlib import Path

import pytest

from scraper.normalize import RawSource, normalize

FIXTURES = Path(__file__).parent / "fixtures"


def load_raw(name: str) -> RawSource:
    d = FIXTURES / name
    teams_file = d / "teams.json"
    teams = json.loads(teams_file.read_text())["data"] if teams_file.exists() else []
    return RawSource(
        teams=teams,
        matches=json.loads((d / "matches.json").read_text())["data"],
        points=json.loads((d / "points.json").read_text())["data"],
    )


@pytest.fixture
def raw_2026() -> RawSource:
    return load_raw("season2026")


@pytest.fixture
def raw_2025() -> RawSource:
    raw = load_raw("season2025_default")
    return RawSource(teams=load_raw("season2026").teams, matches=raw.matches, points=raw.points)


@pytest.fixture
def season_2026(raw_2026) -> dict:
    return normalize(raw_2026)
