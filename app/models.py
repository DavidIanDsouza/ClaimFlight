"""
app/models.py — Pydantic data models for The Flight Delay Extorter
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    """Payload for POST /api/extort/extract"""
    email_text: str = Field(
        ...,
        description="Raw airline delay/cancellation email text to parse",
        min_length=10,
        examples=[
            "Dear valued passenger, Air Canada flight AC123 from CYYZ to CYVR "
            "on July 20 2026 is delayed by 10 hours due to operational disruption."
        ],
    )


class ReconcileRequest(BaseModel):
    """Payload for POST /api/extort/reconcile"""
    claim_id: str = Field(..., description="Claim ID returned by /extract")
    new_status: Optional[str] = Field(
        None,
        description="Optional new status to set (e.g. DISPUTED, SETTLED, CLOSED)",
    )


# ---------------------------------------------------------------------------
# OpenRouter extraction output schema
# ---------------------------------------------------------------------------

class FlightDetails(BaseModel):
    """Structured flight data extracted by OpenRouter from email text."""
    airline: str = Field(..., description="Full airline name (e.g. Air Canada)")
    flight_number: str = Field(..., description="IATA flight code (e.g. AC123)")
    departure_airport: str = Field(
        ...,
        description="Departure airport ICAO or IATA code (e.g. CYYZ or YYZ)",
    )
    arrival_airport: str = Field(
        ...,
        description="Arrival airport ICAO or IATA code (e.g. CYVR or YVR)",
    )
    arrival_city: str = Field(
        ...,
        description="City name of the arrival airport (e.g. Vancouver)",
    )
    delay_duration_hours: float = Field(
        ...,
        description="Total delay in hours (e.g. 10.0)",
        ge=0,
    )
    original_departure_date: str = Field(
        ...,
        description="Original scheduled departure date in YYYY-MM-DD format",
    )
    cancellation: bool = Field(
        default=False,
        description="True if the flight was cancelled rather than delayed",
    )
    reason: Optional[str] = Field(
        None,
        description="Stated reason for the delay/cancellation if mentioned",
    )


# ---------------------------------------------------------------------------
# Regulation engine output
# ---------------------------------------------------------------------------

class EntitlementResult(BaseModel):
    """Output of the regulation engine."""
    jurisdiction: str = Field(..., description="e.g. Canada (APPR), Europe (EU261), USA (DOT)")
    regulation_name: str = Field(..., description="Short regulation name")
    regulation_text: str = Field(..., description="Verbose legal description for the PDF")
    entitlement_amount: float = Field(..., description="Monetary entitlement amount")
    entitlement_currency: str = Field(..., description="ISO currency code: CAD, EUR, USD")
    accommodation_estimate_per_night: float = Field(
        ...,
        description="Estimated hotel cost per night to include in claim",
    )
    accommodation_currency: str = Field(..., description="Same currency as entitlement")


# ---------------------------------------------------------------------------
# Ledger / payment models
# ---------------------------------------------------------------------------

class ClaimBreakdown(BaseModel):
    """Line-item breakdown of the total claim."""
    statutory_entitlement: float
    statutory_entitlement_currency: str
    accommodation_relief: float
    accommodation_relief_currency: str
    meals_and_incidentals: float
    meals_and_incidentals_currency: str
    processing_fee: float
    processing_fee_currency: str
    total_claim: float
    total_claim_currency: str


class LedgerEntry(BaseModel):
    """Synthetic Chexy-style payment ledger record."""
    claim_id: str
    created_at: str  # ISO timestamp
    airline: str
    flight_number: str
    passenger_ref: str  # synthetic reference number
    transit_routing: str  # 9-digit synthetic ABA routing number
    account_number: str  # 10-digit synthetic account
    account_type: str = "CHECKING"
    institution_name: str = "First National Synthetic Bank"
    status: str  # e.g. PENDING_DISPUTE_RESPONSE, DISPUTED, SETTLED, CLOSED
    breakdown: ClaimBreakdown
    notes: str = ""


# ---------------------------------------------------------------------------
# Main response model
# ---------------------------------------------------------------------------

class ClaimResult(BaseModel):
    """Full response returned by POST /api/extort/extract"""
    claim_id: str
    flight_details: FlightDetails
    entitlement: EntitlementResult
    stay22_embed_url: str = Field(..., description="Stay22 iframe embed URL for dashboard")
    stay22_list_url: str = Field(..., description="Stay22 Allez deep-link for direct booking")
    pdf_download_url: str = Field(..., description="URL to download the generated demand PDF")
    ledger_entry: LedgerEntry
    message: str = "Statutory restitution claim generated successfully."
    extraction_source: str = "OpenRouter (free)"


class RebutRequest(BaseModel):
    """Payload for POST /api/extort/rebut"""
    original_claim_id: str = Field(..., description="The original claim reference ID (e.g. FDE-XXXX)")
    rejection_text: str = Field(
        ...,
        description="The raw rejection email or text received from the airline",
        min_length=10,
        examples=[
            "Thank you for contacting us. We have reviewed your claim AC-12345. "
            "Unfortunately, we must deny compensation because the delay was caused by weather."
        ],
    )


class RebutResponse(BaseModel):
    """Response returned by POST /api/extort/rebut"""
    claim_id: str
    rebut_id: str
    loophole_analysis: str = Field(..., description="AI evaluation of the airline's loopholes/excuses")
    rebuttal_letter: str = Field(..., description="Legally-worded follow-up text response")
    pdf_download_url: str = Field(..., description="URL to download the generated rebuttal PDF")
    original_ledger_entry: LedgerEntry
    message: str = "Rebuttal analysis and escalation document generated."


