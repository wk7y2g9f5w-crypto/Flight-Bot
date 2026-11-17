"""Playing-time parsing and conversion to Eastern Time.

Pure functions (no Discord, no database) so they are easy to test.

Members enter their usual playing window in their own timezone; the bot
stores the window and shows it converted to Eastern Time
(America/New_York — EST in winter, EDT in summer) so the roster reads in
one timezone. A window is stored as minutes from midnight in the member's
own timezone, so the conversion is always done from the member's clock.
"""
import re
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

    Returns (start_min, end_min) as minutes from midnight in the
    member's own timezone. An end earlier than the start means the
    window runs past midnight (10pm-1am). Raises ValueError with a
    plain-language message for anything else.
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


def validate_timezone(raw: str) -> str:
    """Check a timezone name and return it as entered (stripped).

    Must be a real IANA name like "America/Denver" — abbreviations
    like "MT" do not pin down a timezone, so they are rejected.
    Raises ValueError with a plain-language message.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("Timezone is empty — enter one like America/Denver.")
    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError:
        raise ValueError(
            f'"{text}" is not a timezone I know — use a full name like '
            "America/Denver, not an abbreviation like MT."
        ) from None
    return text


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


def convert_window_to_eastern(
    start_min: int,
    end_min: int,
    tz_name: str,
    on_date: date | None = None,
) -> tuple[str, str]:
    """Convert a member-local window to Eastern Time.

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


def local_tz_abbrev(tz_name: str, on_date: date | None = None) -> str:
    """The short name of a timezone on a given day, e.g. "MDT"."""
    tz = ZoneInfo(tz_name)
    if on_date is None:
        on_date = datetime.now(tz).date()
    return datetime.combine(on_date, dt_time(12, 0), tzinfo=tz).tzname() or tz_name


def format_eastern_display(days: str, start: str, end: str) -> str:
    """The roster line for a converted window, e.g. "Weeknights 8pm–11pm ET"."""
    return f"{days} {start}–{end} ET"
