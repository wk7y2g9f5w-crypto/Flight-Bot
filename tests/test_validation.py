"""Handicap and tour validation."""
import pytest

from src.validation import normalize_tour, parse_handicap


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12", 12.0),
        ("12.5", 12.5),
        ("0", 0.0),
        ("-2", -2.0),
        ("-10", -10.0),
        ("54", 54.0),
        ("  18.5  ", 18.5),
        ("+3", 3.0),
    ],
)
def test_parse_handicap_accepts(raw, expected):
    assert parse_handicap(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "100", "54.5", "-11", "12.5.3", "NaN", "inf", "twelve"],
)
def test_parse_handicap_rejects(raw):
    with pytest.raises(ValueError):
        parse_handicap(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ProTour", "ProTour"),
        ("protour", "ProTour"),
        ("Accessible", "Accessible"),
        ("accessible", "Accessible"),
        ("Both", "Both"),
        (" both ", "Both"),
    ],
)
def test_normalize_tour_accepts(raw, expected):
    assert normalize_tour(raw) == expected


@pytest.mark.parametrize("raw", ["", "Pro", "Tour", "All", "GGA"])
def test_normalize_tour_rejects(raw):
    with pytest.raises(ValueError):
        normalize_tour(raw)
