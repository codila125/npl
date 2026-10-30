from scraper.normalize import normalize


def test_normalizes_32_matches_numbered_1_to_32(raw_2026):
    season = normalize(raw_2026)
    assert [m["number"] for m in season["matches"]] == list(range(1, 33))


def by_number(season, n):
    return next(m for m in season["matches"] if m["number"] == n)


def test_playoffs_are_numbered_29_to_32_with_labels_and_stages(season_2026):
    playoffs = [by_number(season_2026, n) for n in range(29, 33)]
    got = [(m["label"], m["stage"]) for m in playoffs]
    assert got == [
        ("Qualifier 1", "qualifier_1"),
        ("Eliminator", "eliminator"),
        ("Qualifier 2", "qualifier_2"),
        ("Final", "final"),
    ]
    assert by_number(season_2026, 1)["label"] == "Match 1"
    assert by_number(season_2026, 1)["stage"] == "league"


def test_start_utc_comes_from_played_at(season_2026):
    assert by_number(season_2026, 1)["start_utc"] == "2026-10-26T11:15:00Z"
    starts = {m["start_utc"][11:] for m in season_2026["matches"]}
    assert starts == {"11:15:00Z", "06:45:00Z"}


def test_real_sides_carry_team_identity_and_score(season_2026):
    side1, side2 = by_number(season_2026, 1)["teams"]
    assert side1 == {
        "slug": "lumbini-lions",
        "name": "Lumbini Lions",
        "short": "LUL",
        "placeholder": False,
        "score": "88/3",
        "overs": "9.5",
    }
    assert side2["slug"] == "sudurpaschim-royals"
    assert side2["score"] == "87/10"
    assert side2["overs"] == "17.2"


def test_playoff_placeholder_text_per_stage(season_2026):
    expected = {
        29: ("1st place", "2nd place"),
        30: ("3rd place", "4th place"),
        31: ("Loser of Qualifier 1", "Winner of Eliminator"),
        32: ("Winner of Qualifier 1", "Winner of Qualifier 2"),
    }
    for number, names in expected.items():
        sides = by_number(season_2026, number)["teams"]
        assert tuple(s["name"] for s in sides) == names
        for s in sides:
            assert s["placeholder"] is True
            assert s["slug"] is None and s["short"] is None
            assert s["score"] is None and s["overs"] is None


def test_half_real_half_placeholder_side(raw_2026):
    for m in raw_2026.matches:
        if m["stage"] == "qualifier_2":
            side = m["participants"][0]
            side.update(teamId="t-1", teamName="Karnali Yaks", slug="karnali-yaks", shortCode="KAY")
    q2 = by_number(normalize(raw_2026), 31)
    assert q2["teams"][0]["placeholder"] is False
    assert q2["teams"][0]["name"] == "Karnali Yaks"
    assert q2["teams"][0]["slug"] == "karnali-yaks"
    assert q2["teams"][1]["placeholder"] is True
    assert q2["teams"][1]["name"] == "Winner of Eliminator"


def raw_with(raw, number_label, **changes):
    for m in raw.matches:
        if m["matchNumber"] == number_label:
            m.update(changes)
    return raw


def test_status_mapping(raw_2026):
    season = normalize(raw_2026)
    assert by_number(season, 1)["status"] == "completed"
    start_in = [m for m in raw_2026.matches if m["status"] == "start_in"][0]
    got = by_number(season, int(start_in["matchNumber"].removeprefix("Match ")))
    assert (got["status"], got["status_raw"]) == ("scheduled", "start_in")
    assert by_number(season, 32)["status"] == "scheduled"
    assert by_number(season, 32)["status_raw"] == "scheduled"


def test_unknown_status_is_other_and_keeps_raw(raw_2026):
    raw_with(raw_2026, "Final", status="in_progress")
    final = by_number(normalize(raw_2026), 32)
    assert (final["status"], final["status_raw"]) == ("other", "in_progress")
    assert final["outcome"] is None


def test_decided_match_has_result_outcome_and_winner_slug(season_2026):
    m1 = by_number(season_2026, 1)
    assert m1["result"] == "Lumbini Lions won by 7 wickets"
    assert m1["outcome"] == "result"
    assert m1["winner"] == "lumbini-lions"


def test_scheduled_match_has_null_result_outcome_winner(season_2026):
    final = by_number(season_2026, 32)
    assert (final["result"], final["outcome"], final["winner"]) == (None, None, None)


def test_completed_without_result_or_winner_is_no_result(raw_2026):
    raw_with(raw_2026, "Match 1", result=None, winnerTeamId=None, winnerLabel=None)
    m1 = by_number(normalize(raw_2026), 1)
    assert (m1["status"], m1["result"], m1["winner"], m1["outcome"]) == (
        "completed",
        None,
        None,
        "no_result",
    )


def test_blank_result_is_null(raw_2026):
    raw_with(raw_2026, "Match 1", result="   ", winnerTeamId=None)
    m1 = by_number(normalize(raw_2026), 1)
    assert m1["result"] is None and m1["outcome"] == "no_result"


def test_no_result_text_without_winner_is_no_result(raw_2026):
    raw_with(raw_2026, "Match 1", result="Match abandoned due to rain", winnerTeamId=None)
    m1 = by_number(normalize(raw_2026), 1)
    assert m1["result"] == "Match abandoned due to rain"
    assert m1["outcome"] == "no_result"
    assert m1["winner"] is None


def test_no_result_phrase_case_insensitive(raw_2026):
    raw_with(raw_2026, "Match 1", result="NO RESULT", winnerTeamId=None)
    assert by_number(normalize(raw_2026), 1)["outcome"] == "no_result"


def test_unusual_result_text_without_winner_stays_result(raw_2026):
    raw_with(raw_2026, "Match 1", result="Match tied (Super Over)", winnerTeamId=None)
    assert by_number(normalize(raw_2026), 1)["outcome"] == "result"


def test_match_metadata_is_carried(season_2026):
    m1 = by_number(season_2026, 1)
    assert m1["id"] == "435ca870-c3a0-40ac-a251-5d9f62a084b7"
    assert m1["venue"] == "Tribhuvan University Cricket Ground, Kirtipur"
    assert m1["updated_at"] == "2026-10-26T18:45:25Z"


def test_top_level_header(season_2026):
    assert list(season_2026)[:5] == ["schema_version", "season", "updated_at", "source", "teams"]
    assert season_2026["schema_version"] == 1
    assert season_2026["season"] == {
        "year": 2026,
        "name": "NPL 2026 (Season 3)",
        "timezone": "Asia/Kathmandu",
        "utc_offset": "+05:45",
    }
    assert season_2026["source"] == {"name": "nplt20league.com", "url": "https://nplt20league.com/"}


def test_eight_teams_sorted_by_name(season_2026):
    teams = season_2026["teams"]
    assert len(teams) == 8
    assert [t["name"] for t in teams] == sorted(t["name"] for t in teams)
    assert teams[0] == {"slug": "biratnagar-kings", "name": "Biratnagar Kings", "short": "BIK"}


def test_standings_rows_in_position_order_with_numeric_nrr(season_2026):
    rows = season_2026["standings"]
    assert [r["position"] for r in rows] == list(range(1, 9))
    assert rows[0] == {
        "position": 1,
        "team": "karnali-yaks",
        "played": 2,
        "won": 2,
        "lost": 0,
        "tied": 0,
        "no_result": 0,
        "points": 4,
        "nrr": 0.534,
    }
    assert all(isinstance(r["nrr"], float) for r in rows)


def test_updated_at_is_latest_source_updated_at(season_2026, raw_2026):
    assert season_2026["updated_at"] == "2026-10-29T15:04:01Z"
    # a later match update wins over points rows
    raw_with(raw_2026, "Match 1", updatedAt="2026-10-30T01:02:03.999Z")
    assert normalize(raw_2026)["updated_at"] == "2026-10-30T01:02:03Z"


def test_match_without_updated_at_falls_back_to_season_updated_at(raw_2026):
    raw_with(raw_2026, "Match 1", updatedAt=None)
    season = normalize(raw_2026)
    assert by_number(season, 1)["updated_at"] == season["updated_at"]


def test_normalize_is_deterministic(raw_2026):
    assert normalize(raw_2026) == normalize(raw_2026)
    assert list(normalize(raw_2026)) == [
        "schema_version", "season", "updated_at", "source", "teams", "standings", "matches",
    ]  # fmt: skip
