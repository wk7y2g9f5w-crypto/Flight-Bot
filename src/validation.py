"""Validation helpers for member profile fields.

Pure functions (no Discord, no database) so they are easy to test.
"""
import math

# The three tours a member can prefer. Labels shown in the Discord select.
VALID_TOURS = ("ProTour", "Accessible", "Both")

# World Handicap System maximum is 54.0; allow down to -10 for plus-handicaps.
MIN_HANDICAP = -10.0
MAX_HANDICAP = 54.0


def parse_handicap(raw: str) -> float:
    """Parse a Golf+ handicap string.

    Accepts whole numbers ("12"), decimals ("12.5") and plus-handicaps
    ("+7" or "-7" — a plus-handicap is stored as a negative number, so
    a +7 player is kept as -7.0). Returns the value as a float.

    Raises ValueError with a plain-language message for anything else.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("Handicap is empty — enter a number like 12 or 12.5.")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(
            f'"{text}" is not a number — enter a handicap like 12 or 12.5.'
        ) from None
    if not math.isfinite(value):
        raise ValueError(f'"{text}" is not a valid handicap.')
    if text.startswith("+"):
        # "+7" is a plus-handicap: 7 strokes better than scratch.
        value = -abs(value)
    if value == 0:
        value = 0.0
    if value < MIN_HANDICAP or value > MAX_HANDICAP:
        raise ValueError(
            f"Handicap must be between {MIN_HANDICAP:g} and {MAX_HANDICAP:g}."
        )
    return value


def format_handicap(handicap) -> str:
    """Display a stored handicap the way golfers write it.

    Plus-handicaps (stored negative) show with a "+" ("+7"); scratch
    shows "0"; anything else shows the plain number ("12.5").
    """
    if handicap is None:
        return "—"
    if handicap == 0:
        return "0"
    if handicap < 0:
        return f"+{-handicap:g}"
    return f"{handicap:g}"


def normalize_tour(raw: str) -> str:
    """Normalize a tour name to one of VALID_TOURS (case-insensitive).

    Raises ValueError for anything else.
    """
    text = (raw or "").strip()
    for tour in VALID_TOURS:
        if text.lower() == tour.lower():
            return tour
    raise ValueError(
        f'"{text}" is not a tour — pick ProTour, Accessible, or Both.'
    )
