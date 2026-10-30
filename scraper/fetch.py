"""Fetch the raw source from nplt20league.com and load offline copies.

Implements the fetch-layer rules:

- V1 — robots.txt: 200 → parsed and every fetched URL must be ``can_fetch``;
  404/410 → allowed; 401/403/5xx/network error → the run fails (cannot
  establish permission).
- V2 — every API request returns HTTP 200 after retries; the body parses as
  JSON; the top level is an object with a non-empty list under ``data``.

Rules V3..V16 live in ``validate.py`` and run on the raw source plus the
normalized season once fetching succeeds. ``load_remote`` takes an injected
``requests``-like session so tests never open a socket; when ``session`` is
``None`` it builds a real session. Retries follow the ``urllib3.Retry`` policy
in ``RETRY`` (3 retries on 5xx/connection errors) inside ``_get_json``, which
sleeps between attempts only for the real session.
"""

import json
import time
from pathlib import Path
from urllib import robotparser

import requests
from urllib3.util import Retry

from . import config
from .errors import ScrapeError
from .normalize import RawSource

ROBOTS_URL = f"{config.SOURCE_BASE}/robots.txt"
TEAMS_URL = f"{config.SOURCE_BASE}/api/v1/teams"
MATCHES_URL = f"{config.SOURCE_BASE}/api/v1/matches?season={config.SEASON_YEAR}"
POINTS_URL = f"{config.SOURCE_BASE}/api/v1/points?season={config.SEASON_YEAR}"
_FETCH_URLS = (TEAMS_URL, MATCHES_URL, POINTS_URL)

HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
TIMEOUT = (5, 20)

RETRY = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=("GET",),
)


def _build_session() -> requests.Session:
    # Retries are driven by the loop in `_get_json` (so an injected session can
    # exercise the same path); mounting an HTTPAdapter here would retry twice.
    return requests.Session()


def _check_robots(session) -> None:
    try:
        resp = session.get(ROBOTS_URL, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ScrapeError("V1", f"robots.txt unreachable: {exc}") from exc
    if resp.status_code in (404, 410):
        return  # no robots.txt → everything allowed
    if resp.status_code != 200:
        raise ScrapeError("V1", f"robots.txt returned HTTP {resp.status_code}")
    parser = robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    for url in _FETCH_URLS:
        if not parser.can_fetch(config.USER_AGENT, url):
            raise ScrapeError("V1", f"robots.txt disallows {url}")


def _parse_json(resp, url: str) -> list:
    try:
        body = resp.json()
    except ValueError as exc:
        raise ScrapeError("V2", f"{url} returned a non-JSON body") from exc
    if not isinstance(body, dict) or not isinstance(body.get("data"), list) or not body["data"]:
        raise ScrapeError("V2", f"{url} returned no non-empty `data` list")
    return body["data"]


def _get_json(session, url: str, sleep=None) -> list:
    attempts = RETRY.total + 1
    for attempt in range(attempts):
        try:
            resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            if attempt < RETRY.total:
                if sleep is not None:
                    sleep(RETRY.backoff_factor * (2**attempt))
                continue
            raise ScrapeError("V2", f"{url} unreachable: {exc}") from exc
        if resp.status_code in RETRY.status_forcelist:
            if attempt < RETRY.total:
                if sleep is not None:
                    sleep(RETRY.backoff_factor * (2**attempt))
                continue
            raise ScrapeError("V2", f"{url} returned HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ScrapeError("V2", f"{url} returned HTTP {resp.status_code}")
        return _parse_json(resp, url)
    raise ScrapeError("V2", f"{url} unreachable after retries")


def load_remote(session=None) -> RawSource:
    own_session = session is None
    if own_session:
        session = _build_session()
    sleep = time.sleep if own_session else None
    _check_robots(session)
    teams = _get_json(session, TEAMS_URL, sleep=sleep)
    matches = _get_json(session, MATCHES_URL, sleep=sleep)
    points = _get_json(session, POINTS_URL, sleep=sleep)
    return RawSource(teams=teams, matches=matches, points=points)


def _read_data_file(path: Path) -> list:
    try:
        body = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ScrapeError("V2", f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise ScrapeError("V2", f"{path} has no `data` list")
    return body["data"]


def load_from_dir(path) -> RawSource:
    d = Path(path)
    return RawSource(
        teams=_read_data_file(d / "teams.json"),
        matches=_read_data_file(d / "matches.json"),
        points=_read_data_file(d / "points.json"),
    )
