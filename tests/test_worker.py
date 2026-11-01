"""The live-score Worker must hit the same source, as the same bot, for the same site."""

import re
from pathlib import Path
from urllib.parse import urlsplit

from scraper import config, fetch

WORKER = (Path(__file__).resolve().parent.parent / "worker" / "live.js").read_text()


def _const(name: str) -> str:
    match = re.search(rf'const {name} = "([^"]+)";', WORKER)
    assert match, f"{name} not found in worker/live.js"
    return match.group(1)


def test_worker_uses_scraper_source_and_user_agent():
    assert _const("UPSTREAM") == fetch.MATCHES_URL
    assert _const("USER_AGENT") == config.USER_AGENT


def test_worker_allows_the_published_site_origin():
    site = urlsplit(config.SITE_URL)
    assert f'"{site.scheme}://{site.netloc}"' in WORKER


def test_worker_scorecard_route_targets_the_same_api_and_validates_ids():
    assert _const("SCORECARD_BASE") == f"{config.SOURCE_BASE}/api/v1/matches/"
    assert "/scorecard`" in WORKER
    # Only UUID match ids are proxied, so the route cannot be pointed elsewhere.
    assert "MATCH_ID.test(" in WORKER
