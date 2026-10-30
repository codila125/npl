"""End-to-end CLI: fetch/load -> normalize -> validate -> ics -> publish."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scraper import cli

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
SEASON_2026 = FIXTURES / "season2026"

TEAM_SLUGS = sorted(
    team["slug"] for team in json.loads((SEASON_2026 / "teams.json").read_text())["data"]
)


def run(argv):
    return cli.main(argv)


def site_files(site: Path) -> list[str]:
    return sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())


def expected_layout() -> list[str]:
    return sorted(
        ["data/npl.json", "calendar/npl.ics"]
        + [f"calendar/{slug}.ics" for slug in TEAM_SLUGS]
    )


def test_from_dir_writes_the_full_site_layout(tmp_path, capsys):
    site = tmp_path / "site"
    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 0
    assert site_files(site) == expected_layout()
    out = capsys.readouterr().out
    assert "fetched teams=8 matches=32 standings=8" in out
    assert "changed: data/npl.json" in out


def test_second_run_reports_no_changes_and_rewrites_nothing(tmp_path, capsys):
    site = tmp_path / "site"
    run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)])
    capsys.readouterr()
    before = {p: p.stat().st_mtime_ns for p in site.rglob("*") if p.is_file()}

    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 0
    assert "no changes" in capsys.readouterr().out
    after = {p: p.stat().st_mtime_ns for p in site.rglob("*") if p.is_file()}
    assert after == before


def fixture_dir(tmp_path, name="source", **overrides) -> Path:
    """A copy of the 2026 fixtures with selected files replaced/mutated."""
    source = tmp_path / name
    shutil.copytree(SEASON_2026, source)
    for filename, payload in overrides.items():
        if callable(payload):
            rows = json.loads((source / f"{filename}.json").read_text())
            payload(rows)
            (source / f"{filename}.json").write_text(json.dumps(rows))
        else:
            (source / f"{filename}.json").write_text(json.dumps(payload))
    return source


def test_2025_payload_fails_with_rule_ids_and_writes_nothing(tmp_path, capsys):
    source = fixture_dir(
        tmp_path,
        matches=json.loads((FIXTURES / "season2025_default" / "matches.json").read_text()),
        points=json.loads((FIXTURES / "season2025_default" / "points.json").read_text()),
    )
    site = tmp_path / "site"
    assert run(["--from-dir", str(source), "--site-dir", str(site)]) == 1
    stderr = capsys.readouterr().err
    assert "error: [V3]" in stderr
    assert not site.exists()


def test_31_matches_fails_the_run(tmp_path, capsys):
    source = fixture_dir(tmp_path, matches=lambda rows: rows["data"].pop())
    assert run(["--from-dir", str(source), "--site-dir", str(tmp_path / "site")]) == 1
    assert "error: [V5]" in capsys.readouterr().err


def test_played_at_skew_fails_the_run(tmp_path, capsys):
    def skew(rows):
        rows["data"][0]["playedAt"] = "2026-10-26T10:45:00.000Z"  # 30 min early

    source = fixture_dir(tmp_path, matches=skew)
    assert run(["--from-dir", str(source), "--site-dir", str(tmp_path / "site")]) == 1
    assert "error: [V9]" in capsys.readouterr().err


def test_unreadable_source_exits_one_with_the_fetch_rule(tmp_path, capsys):
    source = fixture_dir(tmp_path, matches="<html>cloudflare</html>")
    assert run(["--from-dir", str(source), "--site-dir", str(tmp_path / "site")]) == 1
    assert "error: [V2]" in capsys.readouterr().err


def test_dry_run_reports_changes_and_writes_nothing(tmp_path, capsys):
    site = tmp_path / "site"
    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would change: data/npl.json" in out
    assert not site.exists()


def test_completed_regression_fails_unless_allowed(tmp_path, capsys):
    site = tmp_path / "site"
    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 0
    data_path = site / "data" / "npl.json"
    previous = json.loads(data_path.read_text())
    for match in previous["matches"]:
        match["status"] = "completed"  # pretend 32 matches were done
    data_path.write_text(json.dumps(previous))
    capsys.readouterr()

    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 1
    assert "error: [V15]" in capsys.readouterr().err

    assert run(
        ["--from-dir", str(SEASON_2026), "--site-dir", str(site), "--allow-regression"]
    ) == 0
    assert "changed: data/npl.json" in capsys.readouterr().out


def test_failure_is_annotated_under_github_actions(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    source = fixture_dir(tmp_path, matches=lambda rows: rows["data"].pop())
    assert run(["--from-dir", str(source), "--site-dir", str(tmp_path / "site")]) == 1
    assert "::error title=V5::" in capsys.readouterr().err


def test_module_entrypoint_runs_offline(tmp_path):
    site = tmp_path / "site"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scraper",
            "--from-dir",
            str(SEASON_2026),
            "--site-dir",
            str(site),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert result.returncode == 0, result.stderr
    assert "fetched teams=8 matches=32 standings=8" in result.stdout
    assert site_files(site) == expected_layout()


def test_unknown_flag_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        run(["--site-dir", str(tmp_path / "site"), "--nope"])
    assert excinfo.value.code == 2


def test_no_result_match_reaches_json_and_calendar(tmp_path):
    def abandoned(rows):
        match = rows["data"][0]
        match["result"] = None
        match["winnerTeamId"] = None
        for participant in match["participants"]:
            participant["score"] = None
            participant["overs"] = None

    source = fixture_dir(tmp_path, matches=abandoned)
    site = tmp_path / "site"
    assert run(["--from-dir", str(source), "--site-dir", str(site)]) == 0
    season = json.loads((site / "data" / "npl.json").read_text())
    match = next(m for m in season["matches"] if m["number"] == 1)
    assert match["outcome"] == "no_result"
    assert match["result"] is None
    calendar = (site / "calendar" / "npl.ics").read_text()
    event = calendar.split("UID:npl-2026-m01@codila125.github.io", 1)[1].split("END:VEVENT")[0]
    assert "Result: No result" in event


def test_stats_reach_the_published_json(tmp_path):
    site = tmp_path / "site"
    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 0
    stats = json.loads((site / "data" / "npl.json").read_text())["stats"]
    assert [len(rows) for rows in stats.values()] == [5, 5, 5, 5]


def test_invalid_stats_keep_previous_stats_and_the_run_succeeds(tmp_path, capsys):
    site = tmp_path / "site"
    assert run(["--from-dir", str(SEASON_2026), "--site-dir", str(site)]) == 0
    published = json.loads((site / "data" / "npl.json").read_text())["stats"]

    def corrupt(rows):
        rows["data"][0]["teamId"] = "not-a-team"

    source = fixture_dir(tmp_path, stats=corrupt)
    capsys.readouterr()
    assert run(["--from-dir", str(source), "--site-dir", str(site)]) == 0
    assert "warning: stats skipped: [V17]" in capsys.readouterr().err
    assert json.loads((site / "data" / "npl.json").read_text())["stats"] == published


def test_missing_stats_without_previous_publishes_null(tmp_path):
    source = fixture_dir(tmp_path)
    (source / "stats.json").unlink()
    site = tmp_path / "site"
    assert run(["--from-dir", str(source), "--site-dir", str(site)]) == 0
    assert json.loads((site / "data" / "npl.json").read_text())["stats"] is None
