from datetime import date, timedelta, timezone

SEASON_YEAR = 2026
SEASON_NAME = "NPL 2026 (Season 3)"
EXPECTED_TEAMS = 8
EXPECTED_MATCHES = 32
STAGES = ("league", "qualifier_1", "eliminator", "qualifier_2", "final")

SOURCE_BASE = "https://nplt20league.com"
USER_AGENT = "npl-calendar-bot/1.0 (+https://github.com/codila125/npl)"
SITE_URL = "https://codila125.github.io/npl/"

NPT = timezone(timedelta(hours=5, minutes=45))
MATCH_DURATION = timedelta(hours=3, minutes=30)
SEASON_WINDOW = (date(2026, 10, 26), date(2026, 11, 21))  # NPT dates, inclusive

SCHEMA_VERSION = 1
