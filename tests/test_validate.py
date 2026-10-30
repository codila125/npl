"""Validation rules V3..V16 (V1/V2 are exercised in test_fetch.py)."""

import copy

from scraper.normalize import normalize
from scraper.validate import validate


def rule_ids(violations):
    return {v.rule_id for v in violations}


def assert_rule(violations, rule_id):
    assert rule_id in rule_ids(violations), f"expected {rule_id}, got {violations}"


def test_golden_2026_data_has_zero_violations(raw_2026):
    season = normalize(raw_2026)
    assert validate(raw_2026, season) == []


def test_v3_season_year_mismatch(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["year"] = 2025
    raw_2026.points[0]["year"] = 2025
    assert_rule(validate(raw_2026, season), "V3")


def test_v4_seven_teams(raw_2026):
    season = normalize(raw_2026)
    raw_2026.teams.pop()
    assert_rule(validate(raw_2026, season), "V4")


def test_v5_31_matches(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches.pop()
    assert_rule(validate(raw_2026, season), "V5")


def test_v6_league_label_out_of_range(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["matchNumber"] = "Match 99"
    assert_rule(validate(raw_2026, season), "V6")


def test_v7_league_match_with_placeholder_side(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["participants"][0]["teamId"] = None
    assert_rule(validate(raw_2026, season), "V7")


def test_v8_nonleague_match_with_unknown_team(raw_2026):
    season = normalize(raw_2026)
    q1 = next(m for m in raw_2026.matches if m["stage"] == "qualifier_1")
    q1["participants"][0]["teamId"] = "bogus-team-id"
    assert_rule(validate(raw_2026, season), "V8")


def test_v9_kickoff_label_mismatch(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["timeLabel"] = "04:00 PM"
    assert_rule(validate(raw_2026, season), "V9")


def test_v9_unparsable_start(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["playedAt"] = "not-a-date"
    assert_rule(validate(raw_2026, season), "V9")


def test_v10_empty_venue(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["venueLabel"] = "   "
    assert_rule(validate(raw_2026, season), "V10")


def test_v11_winner_not_a_participant(raw_2026):
    season = normalize(raw_2026)
    m1 = raw_2026.matches[0]
    m1["winnerTeamId"] = next(
        t["id"] for t in raw_2026.teams if t["id"] not in [p["teamId"] for p in m1["participants"]]
    )
    assert_rule(validate(raw_2026, season), "V11")


def test_v12_standings_math_broken(raw_2026):
    season = normalize(raw_2026)
    raw_2026.points[0]["won"] = 99
    assert_rule(validate(raw_2026, season), "V12")


def test_v12_non_finite_net_run_rate(raw_2026):
    season = normalize(raw_2026)
    raw_2026.points[0]["netRunRate"] = "NaN"
    assert_rule(validate(raw_2026, season), "V12")


def test_v13_all_updated_at_missing(raw_2026):
    season = normalize(raw_2026)
    for m in raw_2026.matches:
        m["updatedAt"] = None
    for p in raw_2026.points:
        p["updatedAt"] = None
    assert_rule(validate(raw_2026, season), "V13")


def test_v13_unparsable_updated_at(raw_2026):
    season = normalize(raw_2026)
    raw_2026.matches[0]["updatedAt"] = "garbage"
    assert_rule(validate(raw_2026, season), "V13")


def test_v14_empty_normalized_matches(raw_2026):
    season = normalize(raw_2026)
    season["matches"] = []
    assert_rule(validate(raw_2026, season), "V14")


def test_v15_regression_guard(raw_2026):
    season = normalize(raw_2026)
    previous = copy.deepcopy(season)
    for m in previous["matches"]:
        m["status"] = "completed"
    assert_rule(validate(raw_2026, season, previous=previous), "V15")


def test_v15_regression_guard_bypassed_by_flag(raw_2026):
    season = normalize(raw_2026)
    previous = copy.deepcopy(season)
    for m in previous["matches"]:
        m["status"] = "completed"
    assert validate(raw_2026, season, previous=previous, allow_regression=True) == []


def test_v15_ignores_different_season(raw_2026):
    season = normalize(raw_2026)
    previous = copy.deepcopy(season)
    previous["season"]["year"] = 2025
    for m in previous["matches"]:
        m["status"] = "completed"
    assert validate(raw_2026, season, previous=previous) == []


def test_v16_control_character(raw_2026):
    season = normalize(raw_2026)
    season["teams"][0]["name"] = "Bad\x00Name"
    assert_rule(validate(raw_2026, season), "V16")


def test_v16_overlong_string(raw_2026):
    season = normalize(raw_2026)
    season["matches"][0]["result"] = "x" * 201
    assert_rule(validate(raw_2026, season), "V16")


def test_completed_without_result_winner_or_scores_is_valid(raw_2026):
    season = normalize(raw_2026)
    m1 = raw_2026.matches[0]
    m1["result"] = None
    m1["winnerTeamId"] = None
    m1["winnerLabel"] = None
    for p in m1["participants"]:
        p["score"] = None
        p["overs"] = None
    assert validate(raw_2026, season) == []


def test_no_result_text_match_is_valid(raw_2026):
    season = normalize(raw_2026)
    m1 = raw_2026.matches[0]
    m1["result"] = "No result"
    m1["winnerTeamId"] = None
    m1["winnerLabel"] = None
    assert validate(raw_2026, season) == []
