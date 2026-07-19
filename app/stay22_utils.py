"""
app/stay22_utils.py — Stay22 Dynamic URL Generator

Builds embeddable iframe links and Allez affiliate deep-links for the
arrival city, automatically anchored to the disruption date.

Affiliate ID: hackthe6ix2026
Documentation: https://dev.stay22.com/docs/maps
"""
from __future__ import annotations

from urllib.parse import quote

STAY22_AID = "hackthe6ix2026"
STAY22_EMBED_BASE = "https://www.stay22.com/embed/gm"
STAY22_ALLEZ_BASE = "https://www.stay22.com/allez"


def build_stay22_embed_url(city: str, checkin_date: str, checkout_date: str | None = None) -> str:
    """
    Build an embeddable Stay22 Maps iframe URL in listview mode.

    Args:
        city: Destination city name (e.g. "Vancouver").
        checkin_date: Check-in date in YYYY-MM-DD format.
        checkout_date: Check-out date (defaults to next day if not provided).

    Returns:
        Full iframe-embeddable URL string.

    Example:
        https://www.stay22.com/embed/gm?aid=hackthe6ix2026&address=Vancouver
        &checkin=2026-07-20&checkout=2026-07-21&viewmode=listview
    """
    if not checkout_date:
        from datetime import date, timedelta
        try:
            ci = date.fromisoformat(checkin_date)
            checkout_date = (ci + timedelta(days=1)).isoformat()
        except ValueError:
            checkout_date = checkin_date  # fallback

    params = (
        f"aid={STAY22_AID}"
        f"&address={quote(city)}"
        f"&checkin={checkin_date}"
        f"&checkout={checkout_date}"
        f"&viewmode=listview"
        f"&currency=auto"
    )
    return f"{STAY22_EMBED_BASE}?{params}"


def build_stay22_list_url(city: str, checkin_date: str, checkout_date: str | None = None) -> str:
    """
    Build a Stay22 Allez affiliate deep-link for direct OTA booking.
    Opens in a new tab on the full Stay22 search UI.

    Args:
        city: Destination city name.
        checkin_date: Check-in date in YYYY-MM-DD format.
        checkout_date: Check-out date (defaults to next day).

    Returns:
        Allez deep-link URL string.
    """
    if not checkout_date:
        from datetime import date, timedelta
        try:
            ci = date.fromisoformat(checkin_date)
            checkout_date = (ci + timedelta(days=1)).isoformat()
        except ValueError:
            checkout_date = checkin_date

    params = (
        f"aid={STAY22_AID}"
        f"&address={quote(city)}"
        f"&checkin={checkin_date}"
        f"&checkout={checkout_date}"
    )
    return f"{STAY22_ALLEZ_BASE}?{params}"


def get_accommodation_label(city: str, checkin_date: str) -> str:
    """Human-readable label for use in PDF demand letters."""
    return (
        f"Emergency Accommodation — {city} — {checkin_date} "
        f"(Stay22 affiliate link: aid={STAY22_AID})"
    )
