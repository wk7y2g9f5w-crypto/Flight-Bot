"""Playing-time parsing and Eastern conversion."""
from datetime import date

import pytest

from src.availability import (
    convert_window_to_eastern,
    format_clock,
    format_eastern_display,
    format_window_local,
    local_tz_abbrev,
    parse_clock,
    parse_window,
    validate_timezone,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6pm", 18 * 60),
        ("6:30pm", 18 * 60 + 30),
        ("6 pm", 18 * 60),
        (" 6 PM ", 18 * 60),
        ("18:00", 18 * 60),
        ("18", 18 * 60),
        ("0", 0),
        ("12am", 0),
        ("12:30am", 30),
        ("12pm", 12 * 60),
        ("12:30pm", 12 * 60 + 30),
        ("11:59pm", 23 * 60 + 59),
    ],
)
def test_parse_clock_accepts(raw, expected):
    assert parse_clock(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "abc", "13pm", "6:60pm", "24:00", "6.30pm", "pm"]
)
def test_parse_clock_rejects(raw):
    with pytest.raises(ValueError):
        parse_clock(raw)


def test_parse_clock_rejects_trailing_junk():
    # "6pm " (trailing space) is fine; "6pmx" is not a time.
    with pytest.raises(ValueError):
        parse_clock("6pmx")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6pm-9pm", (18 * 60, 21 * 60)),
        ("6pm to 9pm", (18 * 60, 21 * 60)),
        ("6pm–9pm", (18 * 60, 21 * 60)),
        ("18:00-21:30", (18 * 60, 21 * 60 + 30)),
        ("10pm-1am", (22 * 60, 60)),
        (" 6:30pm - 9pm ", (18 * 60 + 30, 21 * 60)),
    ],
)
def test_parse_window_accepts(raw, expected):
    assert parse_window(raw) == expected


@pytest.mark.parametrize("raw", ["", "6pm", "6pm-6pm", "evenings", "6pm-", "6pm-9pm-11pm"])
def test_parse_window_rejects(raw):
    with pytest.raises(ValueError):
        parse_window(raw)


@pytest.mark.parametrize("raw", ["America/Denver", "America/New_York", "UTC", "Europe/London"])
def test_validate_timezone_accepts(raw):
    assert validate_timezone(raw) == raw


@pytest.mark.parametrize("raw", ["", "MT", "Denver", "Mars/Olympus"])
def test_validate_timezone_rejects(raw):
    with pytest.raises(ValueError):
        validate_timezone(raw)


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (0, "12am"),
        (30, "12:30am"),
        (720, "12pm"),
        (750, "12:30pm"),
        (1080, "6pm"),
        (1110, "6:30pm"),
        (1439, "11:59pm"),
    ],
)
def test_format_clock(minutes, expected):
    assert format_clock(minutes) == expected


def test_format_window_local():
    assert format_window_local(18 * 60, 21 * 60) == "6pm-9pm"
    assert format_window_local(22 * 60, 60) == "10pm-1am"


def test_convert_denver_to_eastern_winter():
    # Nov 17 2026: Denver is MST (UTC-7), New York is EST (UTC-5).
    assert convert_window_to_eastern(18 * 60, 21 * 60, "America/Denver", date(2026, 11, 17)) == (
        "8pm",
        "11pm",
    )


def test_convert_denver_to_eastern_summer():
    # Jul 15 2026: Denver is MDT (UTC-6), New York is EDT (UTC-4).
    assert convert_window_to_eastern(18 * 60, 21 * 60, "America/Denver", date(2026, 7, 15)) == (
        "8pm",
        "11pm",
    )


def test_convert_west_coast_to_eastern():
    assert convert_window_to_eastern(18 * 60, 21 * 60, "America/Los_Angeles", date(2026, 11, 17)) == (
        "9pm",
        "12am",
    )


def test_convert_window_past_midnight():
    # 10pm-1am Denver in winter becomes 12am-3am Eastern.
    assert convert_window_to_eastern(22 * 60, 60, "America/Denver", date(2026, 11, 17)) == (
        "12am",
        "3am",
    )


def test_convert_eastern_to_eastern_is_identity():
    assert convert_window_to_eastern(18 * 60, 21 * 60, "America/New_York", date(2026, 11, 17)) == (
        "6pm",
        "9pm",
    )


def test_convert_half_hours():
    assert convert_window_to_eastern(
        18 * 60 + 30, 21 * 60 + 30, "America/Denver", date(2026, 11, 17)
    ) == ("8:30pm", "11:30pm")


def test_format_eastern_display():
    assert format_eastern_display("Weeknights", "8pm", "11pm") == "Weeknights 8pm–11pm ET"


def test_local_tz_abbrev_follows_dst():
    assert local_tz_abbrev("America/Denver", date(2026, 11, 17)) == "MST"
    assert local_tz_abbrev("America/Denver", date(2026, 7, 15)) == "MDT"
