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

    Accepts whole numbers ("12"), decimals ("12.5") and negatives for
    plus-handicaps ("-2"). Returns the value as a float.

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
    if value < MIN_HANDICAP or value > MAX_HANDICAP:
        raise ValueError(
            f"Handicap must be between {MIN_HANDICAP:g} and {MAX_HANDICAP:g}."
        )
    return value


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
