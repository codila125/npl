import copy
import re
from datetime import timedelta
from pathlib import Path

from icalendar import Calendar

from scraper.ics import build_calendars, escape_text, fold

ALL_UID = "npl-2026-m01@codila125.github.io"
FINAL_UID = "npl-2026-m32@codila125.github.io"


def by_number(season, n):
    return next(m for m in season["matches"] if m["number"] == n)


def logical_lines(text):
    """Undo RFC 5545 folding and split into logical content lines."""
    return text.replace("\r\n ", "").split("\r\n")


def event_block(text, uid):
    start = text.index(f"UID:{uid}")
    end = text.index("END:VEVENT", start)
    return text[start:end]


def find_event(cal, uid):
    for ev in cal.walk("VEVENT"):
        if str(ev["UID"]) == uid:
            return ev
    raise AssertionError(f"event {uid} not found")


def test_escape_text_backslash_semicolon_comma():
    assert escape_text(r"a\b") == r"a\\b"
    assert escape_text("a;b") == r"a\;b"
    assert escape_text("a,b") == r"a\,b"
    assert escape_text(r"a\b;c,d") == r"a\\b\;c\,d"


def test_escape_text_newlines_become_literal_backslash_n():
    assert escape_text("a\nb") == r"a\nb"
    assert escape_text("a\r\nb") == r"a\nb"
    assert escape_text("a\rb") == r"a\nb"


def test_escape_text_leaves_non_ascii_untouched():
    assert escape_text("Nepal · Kirtipur") == "Nepal · Kirtipur"


def test_fold_leaves_short_lines_alone():
    assert fold("BEGIN:VCALENDAR") == "BEGIN:VCALENDAR"


def test_fold_splits_long_lines_at_utf8_boundaries():
    line = "SUMMARY:" + "Team·" * 30  # "·" is a multibyte UTF-8 character
    folded = fold(line)
    assert "\r\n" in folded
    parts = folded.split("\r\n")
    for part in parts:
        assert len(part.encode("utf-8")) <= 75
    for part in parts[1:]:
        assert part.startswith(" ")
    # Unfolding the physical lines must reproduce the original line exactly.
    rebuilt = "".join(part[1:] if i else part for i, part in enumerate(parts))
    assert rebuilt == line


def test_calendar_is_crlf_only_and_ends_with_crlf(season_2026):
    for data in build_calendars(season_2026).values():
        text = data.decode("utf-8")
        assert text.endswith("\r\n")
        assert "\r\n" in text
        assert not re.search(r"(?<!\r)\n", text), "found a bare LF"
        assert not re.search(r"\r(?!\n)", text), "found a bare CR"


def test_every_physical_line_is_within_75_octets(season_2026):
    for data in build_calendars(season_2026).values():
        for line in data.decode("utf-8").split("\r\n"):
            if line:
                assert len(line.encode("utf-8")) <= 75, line


def test_vevent_counts(season_2026):
    cals = build_calendars(season_2026)
    all_text = cals["calendar/npl.ics"].decode("utf-8")
    assert all_text.count("BEGIN:VEVENT") == 32
    assert all_text.count("END:VEVENT") == 32
    for team in season_2026["teams"]:
        text = cals[f"calendar/{team['slug']}.ics"].decode("utf-8")
        assert text.count("BEGIN:VEVENT") == 7, team["slug"]
        assert text.count("END:VEVENT") == 7, team["slug"]


def test_team_feed_only_contains_that_teams_matches(season_2026):
    cals = build_calendars(season_2026)
    for team in season_2026["teams"]:
        cal = Calendar.from_ical(cals[f"calendar/{team['slug']}.ics"])
        for ev in cal.walk("VEVENT"):
            assert team["name"] in str(ev["SUMMARY"])


def test_uid_format_and_uniqueness(season_2026):
    text = build_calendars(season_2026)["calendar/npl.ics"].decode("utf-8")
    uids = re.findall(r"^UID:([^\r\n]+)", text, flags=re.M)
    assert len(uids) == 32
    assert uids[0] == ALL_UID
    assert uids[-1] == FINAL_UID
    assert len(set(uids)) == 32


def test_same_uid_across_all_and_team_feeds(season_2026):
    cals = build_calendars(season_2026)
    all_uids = set(re.findall(r"UID:(npl-2026-m\d+@codila125\.github\.io)",
                              cals["calendar/npl.ics"].decode("utf-8")))
    for team in season_2026["teams"]:
        team_uids = set(re.findall(r"UID:(npl-2026-m\d+@codila125\.github\.io)",
                                   cals[f"calendar/{team['slug']}.ics"].decode("utf-8")))
        assert team_uids <= all_uids


def test_build_is_deterministic_and_uid_stable_after_result_update(season_2026):
    before = build_calendars(season_2026)
    assert before == build_calendars(season_2026)
    changed = copy.deepcopy(season_2026)
    by_number(changed, 1)["result"] = "Lumbini Lions won by 10 wickets"
    by_number(changed, 1)["updated_at"] = "2026-10-26T19:00:00Z"
    after = build_calendars(changed)
    before_uids = re.findall(r"UID:(npl-2026-m\d+@codila125\.github\.io)",
                             before["calendar/npl.ics"].decode("utf-8"))
    after_uids = re.findall(r"UID:(npl-2026-m\d+@codila125\.github\.io)",
                            after["calendar/npl.ics"].decode("utf-8"))
    assert after_uids == before_uids


def test_unrelated_match_change_does_not_change_other_events(season_2026):
    before = build_calendars(season_2026)["calendar/npl.ics"].decode("utf-8")
    changed = copy.deepcopy(season_2026)
    by_number(changed, 2)["result"] = "Chitwan Rhinos won by 9 runs"
    by_number(changed, 2)["updated_at"] = "2026-10-27T11:00:00Z"
    after = build_calendars(changed)["calendar/npl.ics"].decode("utf-8")
    assert event_block(before, ALL_UID) == event_block(after, ALL_UID)
    assert event_block(before, "npl-2026-m02@codila125.github.io") != \
        event_block(after, "npl-2026-m02@codila125.github.io")


def test_dtend_is_start_plus_three_hours_thirty(season_2026):
    cal = Calendar.from_ical(build_calendars(season_2026)["calendar/npl.ics"])
    for ev in cal.walk("VEVENT"):
        assert ev["DTEND"].dt - ev["DTSTART"].dt == timedelta(hours=3, minutes=30)


def test_summary_and_feed_names(season_2026):
    cals = build_calendars(season_2026)
    all_text = cals["calendar/npl.ics"].decode("utf-8")
    assert "X-WR-CALNAME:NPL 2026 — All matches\r\n" in all_text
    cal = Calendar.from_ical(cals["calendar/npl.ics"])
    assert str(find_event(cal, ALL_UID)["SUMMARY"]) == \
        "Lumbini Lions vs Sudurpaschim Royals (NPL Match 1)"
    assert str(find_event(cal, "npl-2026-m29@codila125.github.io")["SUMMARY"]) == \
        "1st place vs 2nd place (NPL Qualifier 1)"
    lumbini = cals["calendar/lumbini-lions.ics"].decode("utf-8")
    assert "X-WR-CALNAME:NPL 2026 — Lumbini Lions\r\n" in lumbini


def test_description_before_result_day_match(season_2026):
    cal = Calendar.from_ical(build_calendars(season_2026)["calendar/npl.ics"])
    desc = str(find_event(cal, "npl-2026-m07@codila125.github.io")["DESCRIPTION"])
    assert desc == (
        "NPL 2026 · Match 7\n"
        "Kick-off 12:30 PM NPT\n"
        "https://codila125.github.io/npl/"
    )


def test_description_before_result_evening_match(season_2026):
    cal = Calendar.from_ical(build_calendars(season_2026)["calendar/npl.ics"])
    desc = str(find_event(cal, FINAL_UID)["DESCRIPTION"])
    assert desc == (
        "NPL 2026 · Final\n"
        "Kick-off 5:00 PM NPT\n"
        "https://codila125.github.io/npl/"
    )


def test_description_completed_with_result_and_scores(season_2026):
    cal = Calendar.from_ical(build_calendars(season_2026)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Result: Lumbini Lions won by 7 wickets\n"
        "Lumbini Lions 88/3 (9.5 ov)\n"
        "Sudurpaschim Royals 87/10 (17.2 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_description_blank_result_with_winner_names_the_winner(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["outcome"] = "result"
    m1["result"] = None
    assert m1["winner"] == "lumbini-lions"
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Result: Lumbini Lions won\n"
        "Lumbini Lions 88/3 (9.5 ov)\n"
        "Sudurpaschim Royals 87/10 (17.2 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_description_blank_result_without_winner_omits_result_line(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["outcome"] = "result"
    m1["result"] = "   "
    m1["winner"] = None
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Lumbini Lions 88/3 (9.5 ov)\n"
        "Sudurpaschim Royals 87/10 (17.2 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_description_no_result_with_text_and_scores(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["outcome"] = "no_result"
    m1["winner"] = None
    m1["result"] = "Match abandoned due to rain"
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Result: Match abandoned due to rain\n"
        "Lumbini Lions 88/3 (9.5 ov)\n"
        "Sudurpaschim Royals 87/10 (17.2 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_description_no_result_blank_and_missing_scores(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["outcome"] = "no_result"
    m1["winner"] = None
    m1["result"] = None
    for side in m1["teams"]:
        side["score"] = None
        side["overs"] = None
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == "Result: No result\nhttps://codila125.github.io/npl/"


def test_completed_match_omits_score_line_when_score_missing(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["teams"][1]["score"] = None
    m1["teams"][1]["overs"] = None
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Result: Lumbini Lions won by 7 wickets\n"
        "Lumbini Lions 88/3 (9.5 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_completed_match_score_without_overs_omits_the_overs(season_2026):
    season = copy.deepcopy(season_2026)
    m1 = by_number(season, 1)
    m1["teams"][0]["overs"] = None
    cal = Calendar.from_ical(build_calendars(season)["calendar/npl.ics"])
    desc = str(find_event(cal, ALL_UID)["DESCRIPTION"])
    assert desc == (
        "Result: Lumbini Lions won by 7 wickets\n"
        "Lumbini Lions 88/3\n"
        "Sudurpaschim Royals 87/10 (17.2 ov)\n"
        "https://codila125.github.io/npl/"
    )


def test_empty_team_feed_is_a_valid_calendar(season_2026):
    season = copy.deepcopy(season_2026)
    season["teams"] = [{"slug": "lonely-team", "name": "Lonely Team", "short": "LOT"}]
    season["matches"] = []
    cals = build_calendars(season)
    assert set(cals) == {"calendar/npl.ics", "calendar/lonely-team.ics"}
    data = cals["calendar/lonely-team.ics"]
    assert data.decode("utf-8").count("BEGIN:VEVENT") == 0
    assert len(Calendar.from_ical(data).walk("VEVENT")) == 0


def test_icalendar_round_trip_counts_uid_and_utc_start(season_2026):
    cals = build_calendars(season_2026)
    expected = {"calendar/npl.ics": 32}
    for team in season_2026["teams"]:
        expected[f"calendar/{team['slug']}.ics"] = 7
    for rel, data in cals.items():
        cal = Calendar.from_ical(data)
        events = [ev for ev in cal.walk("VEVENT")]
        assert len(events) == expected[rel]
        for ev in events:
            assert str(ev["UID"]).endswith("@codila125.github.io")
            assert ev["DTSTART"].dt.tzinfo is not None
            assert ev["DTSTART"].dt.utcoffset() == timedelta(0)


def test_vevent_property_order(season_2026):
    text = build_calendars(season_2026)["calendar/npl.ics"].decode("utf-8")
    block = event_block(text, ALL_UID)
    names = [line.split(":", 1)[0].split(";", 1)[0] for line in logical_lines(block) if line]
    assert names == [
        "UID", "DTSTAMP", "LAST-MODIFIED", "DTSTART", "DTEND",
        "SUMMARY", "LOCATION", "DESCRIPTION", "URL", "STATUS", "TRANSP",
    ]


def test_header_order(season_2026):
    text = build_calendars(season_2026)["calendar/npl.ics"].decode("utf-8")
    assert text.startswith(
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//codila125//NPL calendar feed//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
    )
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H\r\n" in text
    assert "X-PUBLISHED-TTL:PT1H\r\n" in text


def test_ics_module_reads_no_wall_clock(season_2026):
    src = Path(__file__).parent.parent / "scraper" / "ics.py"
    text = src.read_text()
    for forbidden in ("datetime.now", "datetime.utcnow", "utcnow", "time.time"):
        assert forbidden not in text, forbidden
