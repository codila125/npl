"""The committed site data and feeds are valid and reproducible."""

import json
from pathlib import Path

from scraper import ics
from scraper.fetch import load_from_dir
from scraper.validate import validate

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
FIXTURES = Path(__file__).parent / "fixtures"


def committed_season() -> dict:
    return json.loads((SITE / "data" / "npl.json").read_text())


def test_committed_data_passes_validation():
    season = committed_season()
    raw = load_from_dir(FIXTURES / "season2026")
    assert validate(raw, season) == []


def test_committed_calendars_are_the_generator_output():
    season = committed_season()
    expected = ics.build_calendars(season)
    written = {p.name for p in (SITE / "calendar").glob("*.ics")}
    assert written == {Path(relpath).name for relpath in expected} == {
        "npl.ics",
        *[f"{team['slug']}.ics" for team in season["teams"]],
    }
    for relpath, data in expected.items():
        assert (SITE / relpath).read_bytes() == data
