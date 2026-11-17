"""Playing-time parsing and display in Eastern Time.

Pure functions (no Discord, no database) so they are easy to test.

Members enter their usual playing window in Eastern Time
(America/New_York — EST in winter, EDT in summer), and the window is
stored as minutes from midnight Eastern. ``convert_window_to_eastern``
is kept only to translate windows saved before timezones were removed:
those were stored in the member's own timezone, and the modal prefill
converts them once so nobody's playing time silently shifts.
"""
import re
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

EASTERN_TZ = "America/New_York"

_CLOCK_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([aApP][mM])?\s*$")
_WINDOW_SPLIT_RE = re.compile(r"\s*(?:-|–|—|to)\s*", re.IGNORECASE)


def parse_clock(raw: str) -> int:
    """Parse a clock time like "6pm", "6:30pm" or "18:00".

    Returns minutes from midnight. Raises ValueError with a
    plain-language message for anything else.
    """
    text = (raw or "").strip()
    match = _CLOCK_RE.match(text)
    if not match:
        raise ValueError(
            f'"{text}" is not a time — try something like 6pm or 18:30.'
        )
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if minute > 59:
        raise ValueError(f'"{text}" is not a time — minutes go up to 59.')
    if meridiem:
        if hour < 1 or hour > 12:
            raise ValueError(
                f'"{text}" is not a time — with am/pm the hour is 1 to 12.'
            )
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        raise ValueError(
            f'"{text}" is not a time — without am/pm the hour is 0 to 23.'
        )
    return hour * 60 + minute


def parse_window(raw: str) -> tuple[int, int]:
    """Parse a playing window like "6pm-9pm" or "18:00 to 21:30".

    Returns (start_min, end_min) as minutes from midnight Eastern Time.
    An end earlier than the start means the window runs past midnight
    (10pm-1am). Raises ValueError with a plain-language message for
    anything else.
    """
    text = (raw or "").strip()
    parts = [p for p in _WINDOW_SPLIT_RE.split(text) if p]
    if len(parts) != 2:
        raise ValueError(
            f'"{text}" is not a time window — try something like 6pm-9pm.'
        )
    start = parse_clock(parts[0])
    end = parse_clock(parts[1])
    if start == end:
        raise ValueError("The start and end times are the same.")
    return start, end


def format_clock(minutes: int) -> str:
    """Format minutes from midnight as "6pm", "6:30pm" or "12am"."""
    minutes %= 24 * 60
    hour, minute = divmod(minutes, 60)
    suffix = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    if minute:
        return f"{hour12}:{minute:02d}{suffix}"
    return f"{hour12}{suffix}"


def format_window_local(start_min: int, end_min: int) -> str:
    """Format a stored window back the way a member would type it."""
    return f"{format_clock(start_min)}-{format_clock(end_min)}"


def prefill_window(existing: dict | None) -> str:
    """The window text to prefill a form with from a saved record.

    Stored minutes are Eastern Time already, except for profiles saved
    before timezones were removed — those are converted to Eastern once
    from the stored timezone, so nobody's playing time silently shifts.
    Returns "" when no structured window is stored.
    """
    if not existing:
        return ""
    start_min = existing.get("avail_start_min")
    end_min = existing.get("avail_end_min")
    if start_min is None or end_min is None:
        return ""
    stored_tz = existing.get("timezone")
    if stored_tz:
        try:
            est_start, est_end = convert_window_to_eastern(
                start_min, end_min, stored_tz
            )
            return f"{est_start}-{est_end}"
        except Exception:
            pass
    return format_window_local(start_min, end_min)


def convert_window_to_eastern(
    start_min: int,
    end_min: int,
    tz_name: str,
    on_date: date | None = None,
) -> tuple[str, str]:
    """Convert a window saved in a member's old timezone to Eastern Time.

    Legacy use only — new windows are entered in Eastern Time already.
    Returns (start, end) as "8pm"-style strings in America/New_York.
    A window that runs past midnight stays a window (10pm-1am local
    becomes, say, 12am-3am Eastern). ``on_date`` pins which day the
    conversion is figured from — today in the member's timezone by
    default; pass an explicit date in tests so DST is deterministic.
    """
    tz = ZoneInfo(tz_name)
    eastern = ZoneInfo(EASTERN_TZ)
    if on_date is None:
        on_date = datetime.now(tz).date()
    duration = (end_min - start_min) % (24 * 60)
    start_dt = datetime.combine(
        on_date, dt_time(start_min // 60, start_min % 60), tzinfo=tz
    )
    end_dt = start_dt + timedelta(minutes=duration)
    start_eastern = start_dt.astimezone(eastern)
    end_eastern = end_dt.astimezone(eastern)
    return (
        format_clock(start_eastern.hour * 60 + start_eastern.minute),
        format_clock(end_eastern.hour * 60 + end_eastern.minute),
    )


def format_eastern_display(days: str, start: str, end: str) -> str:
    """The roster line for a window, e.g. "Weeknights 8pm–11pm ET"."""
    return f"{days} {start}–{end} ET"
