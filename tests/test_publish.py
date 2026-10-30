import json
import os

import pytest

from scraper.publish import render_json, write_outputs


def test_render_json_format(season_2026):
    out = render_json(season_2026)
    assert out.endswith(b"}\n") and not out.endswith(b"\n\n")
    text = out.decode("utf-8")
    assert text.startswith('{\n  "schema_version": 1,\n  "season": {\n    "year": 2026,')
    assert "\r" not in text
    assert json.loads(text) == season_2026


def test_render_json_keeps_key_order_and_non_ascii():
    out = render_json({"b": 1, "a": "Nepal · Kirtipur"}).decode("utf-8")
    assert out == '{\n  "b": 1,\n  "a": "Nepal · Kirtipur"\n}\n'


def test_render_json_rejects_non_finite_floats():
    with pytest.raises(ValueError):
        render_json({"netRunRate": float("nan")})


def test_write_creates_files_and_reports_changed_paths(tmp_path):
    changed = write_outputs(tmp_path, {"data/npl.json": b"{}\n", "calendar/npl.ics": b"A\r\n"})
    assert sorted(changed) == ["calendar/npl.ics", "data/npl.json"]
    assert (tmp_path / "data/npl.json").read_bytes() == b"{}\n"
    assert (tmp_path / "calendar/npl.ics").read_bytes() == b"A\r\n"


def test_unchanged_output_rewrites_nothing(tmp_path):
    outputs = {"data/npl.json": b"{}\n", "calendar/npl.ics": b"A\r\n"}
    write_outputs(tmp_path, outputs)
    target = tmp_path / "data/npl.json"
    os.utime(target, (1_000_000, 1_000_000))
    before = target.stat()
    assert write_outputs(tmp_path, outputs) == []
    after = target.stat()
    assert (after.st_mtime, after.st_ino) == (before.st_mtime, before.st_ino)


def test_only_changed_paths_are_rewritten(tmp_path):
    write_outputs(tmp_path, {"data/npl.json": b"{}\n", "calendar/npl.ics": b"A\r\n"})
    changed = write_outputs(tmp_path, {"data/npl.json": b"{}\n", "calendar/npl.ics": b"B\r\n"})
    assert changed == ["calendar/npl.ics"]
    assert (tmp_path / "calendar/npl.ics").read_bytes() == b"B\r\n"


def test_orphan_calendar_files_are_removed(tmp_path):
    write_outputs(tmp_path, {"calendar/npl.ics": b"A", "calendar/old-team.ics": b"B"})
    changed = write_outputs(tmp_path, {"calendar/npl.ics": b"A"})
    assert changed == ["calendar/old-team.ics"]
    assert not (tmp_path / "calendar/old-team.ics").exists()
    assert (tmp_path / "calendar/npl.ics").exists()


def test_non_ics_files_in_calendar_dir_are_left_alone(tmp_path):
    (tmp_path / "calendar").mkdir()
    (tmp_path / "calendar/README.txt").write_text("keep")
    write_outputs(tmp_path, {"calendar/npl.ics": b"A"})
    assert (tmp_path / "calendar/README.txt").read_text() == "keep"


def test_dry_run_writes_and_deletes_nothing_but_reports(tmp_path):
    write_outputs(tmp_path, {"calendar/npl.ics": b"A", "calendar/old.ics": b"B"})
    changed = write_outputs(
        tmp_path, {"calendar/npl.ics": b"A2", "data/npl.json": b"{}\n"}, dry_run=True
    )
    assert sorted(changed) == ["calendar/npl.ics", "calendar/old.ics", "data/npl.json"]
    assert (tmp_path / "calendar/npl.ics").read_bytes() == b"A"
    assert (tmp_path / "calendar/old.ics").exists()
    assert not (tmp_path / "data").exists()


def test_no_temp_files_left_behind(tmp_path):
    write_outputs(tmp_path, {"data/npl.json": b"{}\n", "calendar/npl.ics": b"A"})
    write_outputs(tmp_path, {"data/npl.json": b"[]\n", "calendar/npl.ics": b"B"})
    names = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert names == ["calendar/npl.ics", "data/npl.json"]


def test_written_files_are_world_readable(tmp_path):
    write_outputs(tmp_path, {"data/npl.json": b"{}\n"})
    assert (tmp_path / "data/npl.json").stat().st_mode & 0o777 == 0o644


def test_committed_seed_matches_fixtures(season_2026):
    from pathlib import Path

    from scraper.fetch import load_from_dir
    from scraper.normalize import normalize_stats

    root = Path(__file__).parent.parent
    seed = root / "site/data/npl.json"
    raw = load_from_dir(root / "tests/fixtures/season2026")
    assert seed.read_bytes() == render_json({**season_2026, "stats": normalize_stats(raw)})
