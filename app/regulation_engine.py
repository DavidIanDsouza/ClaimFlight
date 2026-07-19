"""
app/regulation_engine.py — Jurisdiction-aware flight delay entitlement calculator

Routing logic based on departure airport ICAO prefix:
  CY*         → Canada (APPR Section 19)
  ED/LF/EG/EI/EB/EP/EH/ES/EN/EK/EF/EE/EV/EY/UM/LT/LG/LI/LO/LW/LP → Europe (EU261/2004)
  Everything else → USA (US DOT)
"""
from __future__ import annotations

import logging
from app.models import FlightDetails, EntitlementResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ICAO prefix → jurisdiction mapping
# ---------------------------------------------------------------------------
# European country ICAO prefixes (2-letter)
_EU_ICAO_PREFIXES = {
    "ED",  # Germany
    "LF",  # France
    "EG",  # United Kingdom
    "EI",  # Ireland
    "EB",  # Belgium
    "EP",  # Poland
    "EH",  # Netherlands
    "ES",  # Sweden
    "EN",  # Norway
    "EK",  # Denmark
    "EF",  # Finland
    "EE",  # Estonia
    "EV",  # Latvia
    "EY",  # Lithuania
    "UM",  # Belarus (Schengen adjacent)
    "LT",  # Turkey (ECAA)
    "LG",  # Greece
    "LI",  # Italy
    "LO",  # Austria
    "LW",  # North Macedonia
    "LP",  # Portugal
    "LE",  # Spain
    "LS",  # Switzerland
    "LK",  # Czech Republic
    "LZ",  # Slovakia
    "LH",  # Hungary
    "LD",  # Croatia
    "LJ",  # Slovenia
    "LB",  # Bulgaria
    "LR",  # Romania
    "EL",  # Luxembourg
    "LC",  # Cyprus
    "LM",  # Malta
    "LN",  # Monaco
    "LA",  # Albania
    "LQ",  # Bosnia-Herzegovina
    "LY",  # Serbia / Montenegro / Kosovo
    "BI",  # Iceland
    "BG",  # Greenland/Denmark
    "EV",  # Latvia
}

# Canadian ICAO prefix
_CANADA_PREFIX = "CY"


def _get_icao_prefix(airport_code: str) -> str:
    """Return the 2-letter ICAO country prefix from a 4-letter ICAO or 3-letter IATA code."""
    code = airport_code.upper().strip()
    if len(code) == 4:
        return code[:2]
    elif len(code) == 3:
        # IATA → approximate jurisdiction by first letter heuristics
        # C → Canada, E/L/B → Europe-ish, K/P → USA
        first = code[0]
        if first == "C":
            return "CY"  # treat as Canadian
        elif first in ("E", "L", "B"):
            return "EG"  # treat as European
        else:
            return "KZ"  # treat as other
    return code[:2]


def _is_canadian(airport_code: str) -> bool:
    prefix = _get_icao_prefix(airport_code)
    return prefix == _CANADA_PREFIX


def _is_european(airport_code: str) -> bool:
    prefix = _get_icao_prefix(airport_code)
    return prefix in _EU_ICAO_PREFIXES


# ---------------------------------------------------------------------------
# Entitlement calculators
# ---------------------------------------------------------------------------

def _calc_canada(flight: FlightDetails) -> EntitlementResult:
    """
    APPR Section 19 — Air Passenger Protection Regulations (Canada)
    SOR/2019-150, as amended

    Large carrier thresholds (within carrier's control, not safety):
      ≥ 9 hours → $1,000 CAD
      ≥ 6 hours → $700 CAD
      ≥ 3 hours → $400 CAD
      Cancellation treated as maximum delay tier
    """
    hours = flight.delay_duration_hours
    is_cancelled = flight.cancellation

    if is_cancelled or hours >= 9:
        amount = 1000.0
        tier = "≥9 hours or cancellation"
    elif hours >= 6:
        amount = 700.0
        tier = "≥6 hours"
    elif hours >= 3:
        amount = 400.0
        tier = "≥3 hours"
    else:
        amount = 0.0
        tier = "<3 hours (below threshold)"

    regulation_text = (
        f"Pursuant to the Air Passenger Protection Regulations (APPR), SOR/2019-150, "
        f"Section 19, as administered by the Canadian Transportation Agency (CTA), "
        f"passengers subject to a flight delay of {tier} caused by circumstances within "
        f"the carrier's control are entitled to compensation of ${amount:,.0f} CAD. "
        f"This entitlement applies independently of any refund or rebooking obligations "
        f"under Sections 17 and 18 of the APPR, and may be claimed within one year of "
        f"the scheduled departure date by filing a formal complaint with the CTA or "
        f"directly with the carrier."
    )

    return EntitlementResult(
        jurisdiction="Canada (APPR)",
        regulation_name="APPR Section 19 (SOR/2019-150)",
        regulation_text=regulation_text,
        entitlement_amount=amount,
        entitlement_currency="CAD",
        accommodation_estimate_per_night=189.0,
        accommodation_currency="CAD",
    )


def _calc_europe(flight: FlightDetails) -> EntitlementResult:
    """
    EU Regulation 261/2004 — Compensation for denied boarding, cancellation
    or long delay of flights.

    Compensation tiers (Article 7):
      All flights ≤1,500 km: €250
      Intra-EU flights >1,500 km, other flights 1,500–3,500 km: €400
      Other flights >3,500 km (and delay >3h): €600
    """
    hours = flight.delay_duration_hours
    is_cancelled = flight.cancellation

    # Conservative: use maximum tier for demo (long-haul assumption)
    if is_cancelled or hours >= 4:
        amount = 600.0
        tier = "long-haul (>3,500 km) or cancellation"
    elif hours >= 3:
        amount = 400.0
        tier = "medium-haul (1,500–3,500 km), delay ≥3h"
    else:
        amount = 250.0
        tier = "short-haul (≤1,500 km)"

    regulation_text = (
        f"Pursuant to Regulation (EC) No 261/2004 of the European Parliament and of "
        f"the Council, Article 7, passengers departing from an EU airport (or arriving "
        f"at an EU airport on an EU carrier) whose flight is delayed or cancelled are "
        f"entitled to compensation of €{amount:,.0f} for a {tier} route. "
        f"This compensation is payable within 7 days of a written claim submitted to "
        f"the operating air carrier, and may be escalated to the relevant National "
        f"Enforcement Body (NEB) or Alternative Dispute Resolution (ADR) body if the "
        f"carrier fails to respond within 60 days."
    )

    return EntitlementResult(
        jurisdiction="Europe (EU Reg 261/2004)",
        regulation_name="EU Regulation 261/2004 Article 7",
        regulation_text=regulation_text,
        entitlement_amount=amount,
        entitlement_currency="EUR",
        accommodation_estimate_per_night=145.0,
        accommodation_currency="EUR",
    )


def _calc_usa(flight: FlightDetails) -> EntitlementResult:
    """
    US DOT — Denied Boarding Compensation (14 CFR Part 250) and Tarmac Delay rules.

    Involuntary denied boarding (DOT):
      If alternative arrives >2h later (international): 400% of one-way fare, max $1,550
      Note: US has no mandatory delay-only compensation beyond goodwill policies.
      This baseline uses a $650 USD goodwill/DOT baseline estimate.
    """
    hours = flight.delay_duration_hours
    is_cancelled = flight.cancellation

    if is_cancelled or hours >= 6:
        amount = 1550.0
        tier = "severe delay/cancellation (involuntary denied boarding maximum)"
    elif hours >= 2:
        amount = 650.0
        tier = "significant delay — DOT goodwill baseline"
    else:
        amount = 200.0
        tier = "minor delay — carrier goodwill credit"

    regulation_text = (
        f"Pursuant to 14 CFR Part 250 (US DOT Denied Boarding Compensation) and "
        f"the Enhancing Airline Passenger Protections rule (14 CFR Part 259), "
        f"passengers subject to a {tier} are entitled to seek compensation of "
        f"${amount:,.0f} USD from the operating carrier. While US law does not mandate "
        f"delay compensation equivalent to EU261, carriers are contractually and "
        f"reputationally obligated to provide meaningful relief under DOT oversight. "
        f"Passengers may file a complaint with the Aviation Consumer Protection Division "
        f"(ACPD) at airconsumer.dot.gov if the carrier fails to provide adequate remedy."
    )

    return EntitlementResult(
        jurisdiction="USA (US DOT)",
        regulation_name="14 CFR Part 250 / DOT Goodwill Policy",
        regulation_text=regulation_text,
        entitlement_amount=amount,
        entitlement_currency="USD",
        accommodation_estimate_per_night=159.0,
        accommodation_currency="USD",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_entitlement(flight: FlightDetails) -> EntitlementResult:
    """
    Route the flight's departure airport through jurisdiction logic and
    return the applicable entitlement.

    Args:
        flight: Extracted FlightDetails from OpenRouter.

    Returns:
        EntitlementResult with jurisdiction, regulation text, and amount.
    """
    airport = flight.departure_airport
    logger.info(f"Calculating entitlement for departure airport: {airport}")

    if _is_canadian(airport):
        logger.info("Jurisdiction: Canada (APPR)")
        return _calc_canada(flight)
    elif _is_european(airport):
        logger.info("Jurisdiction: Europe (EU261/2004)")
        return _calc_europe(flight)
    else:
        logger.info("Jurisdiction: USA (US DOT)")
        return _calc_usa(flight)
