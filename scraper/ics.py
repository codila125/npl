"""Deterministic iCalendar generation from a normalized Season dict (pure).

`build_calendars` returns ``{relpath: bytes}`` with ``calendar/npl.ics`` and one
``calendar/<slug>.ics`` per team. The output is a pure function of the Season
dict: no wall clock is read anywhere in this module (ADR-2), so two builds from
the same data are byte-identical and an unchanged source yields no diff.
"""

from datetime import datetime

from . import config

LINE_LIMIT = 75  # RFC 5545 §3.1: max octets per physical line, excluding CRLF


def escape_text(value: str) -> str:
    """Escape a TEXT property value per RFC 5545 §3.3.11."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line to at most 75 octets per physical line.

    Lines are broken only at UTF-8 character boundaries; continuation lines
    start with a single space, which counts toward their 75 octets.
    """
    if len(line.encode("utf-8")) <= LINE_LIMIT:
        return line
    physical: list[str] = []
    current = ""
    current_len = 0
    for ch in line:
        ch_len = len(ch.encode("utf-8"))
        budget = LINE_LIMIT if not physical else LINE_LIMIT - 1
        if current_len + ch_len > budget:
            physical.append((" " if physical else "") + current)
            current = ""
            current_len = 0
        current += ch
        current_len += ch_len
    physical.append((" " if physical else "") + current)
    return "\r\n".join(physical)


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _ics_time(iso: str) -> str:
    return _utc(iso).strftime("%Y%m%dT%H%M%SZ")


def _dtend(start_utc: str) -> str:
    return (_utc(start_utc) + config.MATCH_DURATION).strftime("%Y%m%dT%H%M%SZ")


def _npt_kickoff(start_utc: str) -> str:
    dt = _utc(start_utc).astimezone(config.NPT)
    hour = dt.hour % 12 or 12
    period = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {period}"


def _uid(year: int, number: int) -> str:
    return f"npl-{year}-m{number:02d}@codila125.github.io"


def _summary(match: dict) -> str:
    side1, side2 = match["teams"][0]["name"], match["teams"][1]["name"]
    return f"{side1} vs {side2} (NPL {match['label']})"


def _description(match: dict, year: int) -> str:
    lines: list[str] = []
    if match["status"] != "completed":
        lines.append(f"NPL {year} · {match['label']}")
        lines.append(f"Kick-off {_npt_kickoff(match['start_utc'])} NPT")
    else:
        lines.append(f"Result: {match['result'] or 'No result'}")
        for side in match["teams"]:
            if side["score"] is not None:
                lines.append(f"{side['name']} {side['score']} ({side['overs']} ov)")
    lines.append(config.SITE_URL)
    return "\n".join(lines)


def _vevent(match: dict, year: int) -> str:
    dtstamp = _ics_time(match["updated_at"])
    lines = [
        "BEGIN:VEVENT",
        f"UID:{_uid(year, match['number'])}",
        f"DTSTAMP:{dtstamp}",
        f"LAST-MODIFIED:{dtstamp}",
        f"DTSTART:{_ics_time(match['start_utc'])}",
        f"DTEND:{_dtend(match['start_utc'])}",
        f"SUMMARY:{escape_text(_summary(match))}",
        f"LOCATION:{escape_text(match.get('venue') or '')}",
        f"DESCRIPTION:{escape_text(_description(match, year))}",
        f"URL:{config.SITE_URL}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]
    return "\r\n".join(fold(line) for line in lines)


def _calendar(name: str, matches: list[dict], year: int) -> bytes:
    lines = [
        fold("BEGIN:VCALENDAR"),
        fold("VERSION:2.0"),
        fold("PRODID:-//codila125//NPL calendar feed//EN"),
        fold("CALSCALE:GREGORIAN"),
        fold("METHOD:PUBLISH"),
        fold(f"X-WR-CALNAME:{escape_text(name)}"),
        fold(
            "X-WR-CALDESC:"
            f"Nepal Premier League {year} match schedule and results. "
            "Times are shown in your own time zone."
        ),
        fold("REFRESH-INTERVAL;VALUE=DURATION:PT1H"),
        fold("X-PUBLISHED-TTL:PT1H"),
    ]
    for match in matches:
        lines.append(_vevent(match, year))
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def build_calendars(season: dict) -> dict[str, bytes]:
    """Return every calendar file as ``{relpath: bytes}`` for a Season dict."""
    year = season["season"]["year"]
    matches = sorted(season["matches"], key=lambda m: (m["start_utc"], m["number"]))
    outputs = {"calendar/npl.ics": _calendar(f"NPL {year} — All matches", matches, year)}
    for team in sorted(season["teams"], key=lambda t: t["slug"]):
        slug = team["slug"]
        team_matches = [
            m for m in matches if any(side.get("slug") == slug for side in m["teams"])
        ]
        outputs[f"calendar/{slug}.ics"] = _calendar(
            f"NPL {year} — {team['name']}", team_matches, year
        )
    return outputs
