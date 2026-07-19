"""
app/payment_ledger.py — Mock Chexy-style Payment Ledger

Generates synthetic ledger entries with realistic-looking banking details
and claim breakdowns. All data is fabricated — no real money moves.

Compliant with Chexy prize track requirement: sandbox/synthetic data only.
"""
from __future__ import annotations

import random
import string
import logging
from datetime import datetime, timezone

from app.models import FlightDetails, EntitlementResult, ClaimBreakdown, LedgerEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory ledger store (resets on server restart — intentional for demo)
# ---------------------------------------------------------------------------
LEDGER: dict[str, LedgerEntry] = {}

# Valid claim status values
VALID_STATUSES = [
    "PENDING_DISPUTE_RESPONSE",
    "UNDER_REVIEW",
    "DISPUTED",
    "ESCALATED",
    "APPROVED",
    "SETTLED",
    "CLOSED",
    "REJECTED",
]

# Synthetic institution names for variety
_INSTITUTIONS = [
    "First National Synthetic Bank",
    "Hackathon Federal Credit Union",
    "Demo Trust & Savings",
    "Placeholder Financial Corp",
    "Mock Capital Reserve",
]

# Real-ish looking ABA routing number prefixes (they won't pass the checksum but look real)
_ROUTING_PREFIXES = ["021", "026", "061", "071", "091", "101", "111", "121", "241"]


def _generate_routing_number() -> str:
    """Generate a 9-digit synthetic ABA routing number."""
    prefix = random.choice(_ROUTING_PREFIXES)
    suffix = "".join(random.choices(string.digits, k=6))
    return f"{prefix}{suffix}"


def _generate_account_number() -> str:
    """Generate a 10-digit synthetic account number."""
    return "".join(random.choices(string.digits, k=10))


def _generate_passenger_ref(claim_id: str) -> str:
    """Generate a synthetic passenger/booking reference code."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PNR-{suffix}"


def _calculate_breakdown(entitlement: EntitlementResult) -> ClaimBreakdown:
    """
    Calculate a full claim breakdown including accommodation, meals, and fees.

    All amounts are in the same currency as the statutory entitlement.
    """
    currency = entitlement.entitlement_currency

    statutory = entitlement.entitlement_amount
    accommodation = round(entitlement.accommodation_estimate_per_night * 1.0, 2)
    meals = round(statutory * 0.08, 2)       # ~8% for meals/incidentals
    processing_fee = round(statutory * 0.03, 2)  # 3% administrative processing

    total = round(statutory + accommodation + meals + processing_fee, 2)

    return ClaimBreakdown(
        statutory_entitlement=statutory,
        statutory_entitlement_currency=currency,
        accommodation_relief=accommodation,
        accommodation_relief_currency=currency,
        meals_and_incidentals=meals,
        meals_and_incidentals_currency=currency,
        processing_fee=processing_fee,
        processing_fee_currency=currency,
        total_claim=total,
        total_claim_currency=currency,
    )


def create_ledger_entry(
    claim_id: str,
    flight: FlightDetails,
    entitlement: EntitlementResult,
) -> LedgerEntry:
    """
    Create and store a new synthetic ledger entry for a claim.

    Args:
        claim_id: Unique claim identifier.
        flight: Extracted flight details.
        entitlement: Calculated entitlement from regulation engine.

    Returns:
        LedgerEntry — stored in the in-memory LEDGER dict.
    """
    breakdown = _calculate_breakdown(entitlement)

    entry = LedgerEntry(
        claim_id=claim_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        airline=flight.airline,
        flight_number=flight.flight_number,
        passenger_ref=_generate_passenger_ref(claim_id),
        transit_routing=_generate_routing_number(),
        account_number=_generate_account_number(),
        account_type="CHECKING",
        institution_name=random.choice(_INSTITUTIONS),
        status="PENDING_DISPUTE_RESPONSE",
        breakdown=breakdown,
        notes=(
            f"Claim filed under {entitlement.regulation_name}. "
            f"Jurisdiction: {entitlement.jurisdiction}. "
            f"Delay: {flight.delay_duration_hours}h on {flight.original_departure_date}."
        ),
    )

    LEDGER[claim_id] = entry
    logger.info(f"Ledger entry created: {claim_id} — {breakdown.total_claim} {breakdown.total_claim_currency}")
    return entry


def get_ledger_entry(claim_id: str) -> LedgerEntry | None:
    """Retrieve a ledger entry by claim ID. Returns None if not found."""
    return LEDGER.get(claim_id)


def update_ledger_status(claim_id: str, new_status: str) -> LedgerEntry | None:
    """
    Update the status of an existing ledger entry.

    Args:
        claim_id: The claim to update.
        new_status: New status string (e.g. DISPUTED, SETTLED).

    Returns:
        Updated LedgerEntry, or None if claim not found.
    """
    entry = LEDGER.get(claim_id)
    if entry is None:
        return None

    status_upper = new_status.upper()
    if status_upper not in VALID_STATUSES:
        logger.warning(f"Unknown status '{new_status}' — setting anyway.")

    entry.status = status_upper
    entry.notes += f" | Status updated to {status_upper} at {datetime.now(timezone.utc).isoformat()}"
    LEDGER[claim_id] = entry
    logger.info(f"Ledger {claim_id} status → {status_upper}")
    return entry


def list_all_entries() -> list[LedgerEntry]:
    """Return all ledger entries ordered by creation time (newest first)."""
    entries = list(LEDGER.values())
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries
