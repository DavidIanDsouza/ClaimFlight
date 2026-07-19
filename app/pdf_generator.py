"""
app/pdf_generator.py — ReportLab PDF Demand Letter Generator

Generates a formally structured, heavily-worded "Demand for Statutory Restitution"
PDF document incorporating:
  - Flight summary and extracted details
  - Applicable jurisdiction and regulation
  - Itemized claim breakdown (statutory + accommodation + meals + fees)
  - Stay22 accommodation URL as "Mandatory Additional Relief"
  - Legal boilerplate and response deadline
"""
from __future__ import annotations

import os
import logging
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT

from app.models import FlightDetails, EntitlementResult, LedgerEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
PDF_OUTPUT_DIR = Path("generated_pdfs")
PDF_OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
DARK_NAVY = colors.HexColor("#0D1B2A")
ACCENT_RED = colors.HexColor("#C0392B")
ACCENT_BLUE = colors.HexColor("#1A5276")
LIGHT_GREY = colors.HexColor("#F2F3F4")
MID_GREY = colors.HexColor("#BDC3C7")
TEXT_DARK = colors.HexColor("#1C2833")
GOLD = colors.HexColor("#B7950B")


def _build_styles() -> dict:
    base = getSampleStyleSheet()

    styles = {
        "firm_header": ParagraphStyle(
            "firm_header",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=MID_GREY,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=ACCENT_RED,
            spaceBefore=6,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "doc_subtitle": ParagraphStyle(
            "doc_subtitle",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=DARK_NAVY,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=ACCENT_BLUE,
            spaceBefore=6,
            spaceAfter=2,
            borderPad=2,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=TEXT_DARK,
            spaceAfter=2,
            alignment=TA_LEFT,
        ),
        "body_bold": ParagraphStyle(
            "body_bold",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=TEXT_DARK,
            spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "small",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MID_GREY,
            spaceAfter=2,
            alignment=TA_LEFT,
        ),
        "url_style": ParagraphStyle(
            "url_style",
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=ACCENT_BLUE,
            spaceAfter=2,
        ),
        "amount_big": ParagraphStyle(
            "amount_big",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=ACCENT_RED,
            alignment=TA_CENTER,
            spaceBefore=6,
            spaceAfter=2,
        ),
        "reference": ParagraphStyle(
            "reference",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MID_GREY,
            alignment=TA_RIGHT,
        ),
    }
    return styles


def _table_style_base() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.4, MID_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])


def _kv_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.4, MID_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])


def _format_airport_code(code: str) -> str:
    c = code.upper().strip()
    mapping = {
        "CYYZ": "YYZ (Toronto)", "YYZ": "YYZ (Toronto)",
        "CYVR": "YVR (Vancouver)", "YVR": "YVR (Vancouver)",
        "CYYC": "YYC (Calgary)", "YYC": "YYC (Calgary)",
        "CYUL": "YUL (Montreal)", "YUL": "YUL (Montreal)",
        "EDDF": "FRA (Frankfurt)", "FRA": "FRA (Frankfurt)",
        "EGLL": "LHR (London)", "LHR": "LHR (London)",
        "KATL": "ATL (Atlanta)", "ATL": "ATL (Atlanta)",
        "KLAX": "LAX (Los Angeles)", "LAX": "LAX (Los Angeles)",
    }
    if c in mapping:
        return mapping[c]
    if len(c) == 4 and (c.startswith("C") or c.startswith("K")):
        return c[1:]
    return c


def generate_demand_pdf(
    claim_id: str,
    flight: FlightDetails,
    entitlement: EntitlementResult,
    ledger: LedgerEntry,
    stay22_list_url: str,
    stay22_embed_url: str,
) -> str:
    """
    Generate a formal "Demand for Statutory Restitution" PDF.

    Args:
        claim_id: Unique claim identifier (used as filename).
        flight: Extracted flight details.
        entitlement: Calculated jurisdiction/entitlement.
        ledger: Synthetic payment ledger entry.
        stay22_list_url: Stay22 Allez booking deep-link.
        stay22_embed_url: Stay22 iframe embed URL.

    Returns:
        Absolute file path of the generated PDF.
    """
    output_path = PDF_OUTPUT_DIR / f"{claim_id}.pdf"
    styles = _build_styles()
    today = date.today()
    response_deadline = (today + timedelta(days=14)).strftime("%B %d, %Y")
    today_str = today.strftime("%B %d, %Y")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=f"Demand for Statutory Restitution — {claim_id}",
        author="ClaimFlight",
        subject=f"Flight {flight.flight_number} — {entitlement.jurisdiction}",
    )

    story = []
    W = 6.8 * inch  # usable width

    # -------------------------------------------------------------------------
    # Header — Law firm letterhead style
    # -------------------------------------------------------------------------
    story.append(Paragraph("CLAIMFLIGHT", styles["firm_header"]))
    story.append(Paragraph(
        "Automated Statutory Restitution Services | hackthe6ix2026",
        styles["firm_header"],
    ))
    story.append(Spacer(1, 2))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT_RED))
    story.append(Spacer(1, 3))

    # Reference line
    story.append(Paragraph(
        f"CLAIM REF: {claim_id}  |  DATE: {today_str}  |  PASSENGER REF: {ledger.passenger_ref}",
        styles["reference"],
    ))
    story.append(Spacer(1, 4))

    dep_fmt = _format_airport_code(flight.departure_airport)
    arr_fmt = _format_airport_code(flight.arrival_airport)

    # -------------------------------------------------------------------------
    # Document title
    # -------------------------------------------------------------------------
    story.append(Paragraph("DEMAND FOR STATUTORY RESTITUTION", styles["doc_title"]))
    story.append(Paragraph(
        f"FLIGHT {flight.flight_number} — {dep_fmt} → {arr_fmt}",
        styles["doc_subtitle"],
    ))
    story.append(Paragraph(
        f"Applicable Regulation: {entitlement.regulation_name}",
        styles["doc_subtitle"],
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))

    # -------------------------------------------------------------------------
    # Total claim amount — prominently displayed
    # -------------------------------------------------------------------------
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        f"TOTAL STATUTORY CLAIM: {ledger.breakdown.total_claim:,.2f} {ledger.breakdown.total_claim_currency}",
        styles["amount_big"],
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 3))

    # -------------------------------------------------------------------------
    # Section 1 — Addressee & Parties
    # -------------------------------------------------------------------------
    story.append(Paragraph("I. PARTIES AND NOTICE", styles["section_heading"]))
    story.append(Paragraph(
        f"TO: {flight.airline} — Legal & Customer Relations Department",
        styles["body_bold"],
    ))
    story.append(Paragraph(
        f"RE: Formal Demand for Statutory Compensation — Flight {flight.flight_number}",
        styles["body_bold"],
    ))
    story.append(Paragraph(
        f"FROM: The undersigned passenger/authorized representative (Claim ID: {claim_id})",
        styles["body_bold"],
    ))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"NOTICE IS HEREBY GIVEN that the undersigned passenger presents this formal, "
        f"legally-grounded demand for immediate statutory compensation arising from the "
        f"disruption of Flight {flight.flight_number} operated by {flight.airline} on "
        f"{flight.original_departure_date}. This demand is issued pursuant to the mandatory "
        f"consumer protection regulations set forth herein and must be responded to in writing "
        f"no later than <b>{response_deadline}</b> (14 calendar days from the date of this notice).",
        styles["body"],
    ))

    # -------------------------------------------------------------------------
    # Section 2 — Flight Details
    # -------------------------------------------------------------------------
    story.append(Paragraph("II. FLIGHT PARTICULARS", styles["section_heading"]))

    cancellation_str = "CANCELLED" if flight.cancellation else f"DELAYED {flight.delay_duration_hours:.1f} HOURS"
    reason_str = flight.reason if flight.reason else "Not disclosed by carrier"

    flight_data = [
        ["Field", "Details"],
        ["Airline / Carrier", flight.airline],
        ["Flight Number", flight.flight_number],
        ["Departure Airport", dep_fmt],
        ["Arrival Airport", arr_fmt],
        ["Arrival City", flight.arrival_city],
        ["Scheduled Departure Date", flight.original_departure_date],
        ["Disruption Type", cancellation_str],
        ["Stated Reason", reason_str],
        ["Applicable Jurisdiction", entitlement.jurisdiction],
    ]

    flight_table = Table(flight_data, colWidths=[2.5 * inch, 4.3 * inch])
    flight_table.setStyle(_kv_table_style())
    story.append(KeepTogether([flight_table]))

    # -------------------------------------------------------------------------
    # Section 3 — Legal Basis
    # -------------------------------------------------------------------------
    story.append(Paragraph("III. LEGAL BASIS AND APPLICABLE REGULATION", styles["section_heading"]))
    story.append(Paragraph(entitlement.regulation_text, styles["body"]))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"The disruption described above satisfies all statutory criteria for mandatory "
        f"compensation under {entitlement.regulation_name}. The carrier's obligation to "
        f"compensate the undersigned passenger is non-negotiable and cannot be waived by "
        f"extraordinary circumstances unless the carrier can demonstrate, by preponderance "
        f"of evidence, that the disruption was caused by events entirely outside its operational "
        f"control and that all reasonable mitigating measures were undertaken.",
        styles["body"],
    ))

    # -------------------------------------------------------------------------
    # Section 4 — Itemized Claim
    # -------------------------------------------------------------------------
    story.append(Paragraph("IV. ITEMIZED CLAIM FOR RESTITUTION", styles["section_heading"]))

    bd = ledger.breakdown
    curr = bd.total_claim_currency

    claim_data = [
        ["Line Item", "Description", f"Amount ({curr})"],
        [
            "1. Statutory Entitlement",
            f"{entitlement.regulation_name}",
            f"{bd.statutory_entitlement:,.2f}",
        ],
        [
            "2. Emergency Accommodation Relief",
            f"Mandatory hotel stay, {flight.arrival_city} ({flight.original_departure_date})",
            f"{bd.accommodation_relief:,.2f}",
        ],
        [
            "3. Meals & Incidentals",
            "Subsistence during delay/cancellation period",
            f"{bd.meals_and_incidentals:,.2f}",
        ],
        [
            "4. Administrative Processing",
            "Claim filing and documentation costs",
            f"{bd.processing_fee:,.2f}",
        ],
        ["TOTAL CLAIM", "", f"{bd.total_claim:,.2f} {curr}"],
    ]

    claim_table = Table(claim_data, colWidths=[2.4 * inch, 2.8 * inch, 1.6 * inch])
    claim_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, 4), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 4), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, 4), [colors.white, LIGHT_GREY]),
        
        # Style the Total Claim row
        ("SPAN", (0, 5), (1, 5)),
        ("BACKGROUND", (0, 5), (-1, 5), DARK_NAVY),
        ("TEXTCOLOR", (0, 5), (-1, 5), colors.white),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
        ("FONTSIZE", (0, 5), (-1, 5), 10),
        ("ALIGN", (2, 5), (2, 5), "RIGHT"),
        
        ("GRID", (0, 0), (-1, -1), 0.4, MID_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    claim_table.setStyle(claim_style)
    story.append(KeepTogether([claim_table]))

    # -------------------------------------------------------------------------
    # Section 5 — Stay22 Accommodation Relief (the big brain move)
    # -------------------------------------------------------------------------
    story.append(Paragraph("V. MANDATORY ACCOMMODATION RELIEF — STAY22 VERIFIED RATES", styles["section_heading"]))
    story.append(Paragraph(
        f"In accordance with the duty of care obligations imposed upon {flight.airline} "
        f"under {entitlement.regulation_name}, the carrier is obligated to provide or "
        f"reimburse the cost of emergency accommodation for affected passengers. "
        f"The following verified accommodation inventory for <b>{flight.arrival_city}</b> "
        f"on <b>{flight.original_departure_date}</b> has been sourced via Stay22's real-time "
        f"aggregation platform (covering Booking.com, Expedia, Hotels.com, and VRBO). "
        f"The passenger hereby formally claims accommodation relief at prevailing market rates "
        f"as itemized in Section IV above.",
        styles["body"],
    ))
    story.append(Spacer(1, 2))

    stay22_data = [
        ["Accommodation Search", "Details"],
        ["Destination City", flight.arrival_city],
        ["Check-in Date", flight.original_departure_date],
        ["Claim Reference (Affiliate ID)", f"hackthe6ix2026 (Stay22)"],
        ["Live Booking Search URL", Paragraph(f'<a href="{stay22_list_url}" color="#1a56db"><b>Book Hotels on Stay22</b></a>', styles["body"])],
        ["Embed URL (Dashboard)", Paragraph(f'<a href="{stay22_embed_url}" color="#1a56db"><b>View Stay22 Live Map</b></a>', styles["body"])],
    ]

    stay22_table = Table(stay22_data, colWidths=[2.5 * inch, 4.3 * inch])
    stay22_table.setStyle(_kv_table_style())
    story.append(KeepTogether([stay22_table]))

    story.append(Spacer(1, 2))
    story.append(Paragraph("Full accommodation search URL:", styles["body_bold"]))
    story.append(Paragraph(f'<a href="{stay22_list_url}" color="#1a56db">Click here to search and book emergency hotels on Stay22</a>', styles["body"]))

    # -------------------------------------------------------------------------
    # Section 6 — Payment Instructions (Chexy Ledger)
    # -------------------------------------------------------------------------
    story.append(Paragraph("VI. PAYMENT INSTRUCTIONS AND LEDGER REFERENCE", styles["section_heading"]))
    story.append(Paragraph(
        f"The undersigned demands that payment of the total claim amount of "
        f"<b>{bd.total_claim:,.2f} {curr}</b> be remitted to the designated account "
        f"within <b>14 calendar days</b> of receipt of this notice. Failure to remit "
        f"payment within the prescribed period will result in immediate escalation to "
        f"the relevant regulatory authority and/or civil claims tribunal without further notice.",
        styles["body"],
    ))
    story.append(Spacer(1, 2))

    payment_data = [
        ["Payment Field", "Details"],
        ["Claim ID", ledger.claim_id],
        ["Passenger Reference", ledger.passenger_ref],
        ["Institution", ledger.institution_name],
        ["Account Type", ledger.account_type],
        ["Transit / ABA Routing Number", ledger.transit_routing],
        ["Account Number", f"****{ledger.account_number[-4:]}"],  # masked
        ["Total Amount Due", f"{bd.total_claim:,.2f} {curr}"],
        ["Payment Status", ledger.status],
        ["Response Deadline", response_deadline],
    ]

    payment_table = Table(payment_data, colWidths=[2.5 * inch, 4.3 * inch])
    payment_table.setStyle(_kv_table_style())
    story.append(KeepTogether([payment_table]))

    # -------------------------------------------------------------------------
    # Section 7 — Legal Boilerplate & Disclaimer
    # -------------------------------------------------------------------------
    story.append(Paragraph("VII. LEGAL NOTICE AND RESERVATION OF RIGHTS", styles["section_heading"]))
    story.append(Paragraph(
        f"The undersigned reserves all rights at law and in equity, including but not limited to "
        f"the right to pursue alternative dispute resolution, regulatory complaint, or judicial "
        f"proceedings in the event of non-compliance with this demand. This notice constitutes a "
        f"formal legal demand and is not a preliminary communication. Time is of the essence. "
        f"All correspondence in response to this demand must reference Claim ID <b>{claim_id}</b> "
        f"and must be directed to the address or electronic means provided separately by the "
        f"undersigned. The carrier's failure to respond shall be deemed an admission of the "
        f"passenger's entitlement and may be relied upon in any subsequent proceeding.",
        styles["body"],
    ))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "⚠️  SANDBOX DISCLAIMER: This document was generated by an automated hackathon "
        "demonstration system. It does not constitute legal advice. No real money has been "
        "transferred. All banking details are synthetically generated. Built at Hack the 6ix "
        "2026 using OpenRouter AI, Stay22, and Chexy-inspired payment tracking.",
        styles["small"],
    ))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"Document generated: {today_str}  |  Claim ID: {claim_id}  |  "
        f"System: ClaimFlight v1.0 (hackthe6ix2026)",
        styles["small"],
    ))

    doc.build(story)
    logger.info(f"PDF generated: {output_path}")
    return str(output_path.resolve())


def generate_rebuttal_pdf(
    rebut_id: str,
    claim_id: str,
    flight: FlightDetails,
    rebuttal_text: str,
    ledger: LedgerEntry,
) -> str:
    """
    Generate a formal "Second Notice: Escalation & Rebuttal Letter" PDF.
    """
    output_path = PDF_OUTPUT_DIR / f"{rebut_id}.pdf"
    styles = _build_styles()
    today_str = date.today().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=f"Second Notice: Escalation & Rebuttal — {rebut_id}",
        author="ClaimFlight",
    )

    story = []

    # Header Letterhead
    story.append(Paragraph("CLAIMFLIGHT", styles["firm_header"]))
    story.append(Paragraph(
        "Automated Restitution Escrow & Arbitration Services | hackthe6ix2026",
        styles["firm_header"],
    ))
    story.append(Spacer(1, 2))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD))
    story.append(Spacer(1, 3))

    # Reference block
    story.append(Paragraph(
        f"REBUTTAL REF: {rebut_id}  |  ORIGINAL CLAIM: {claim_id}  |  DATE: {today_str}",
        styles["reference"],
    ))
    story.append(Spacer(1, 4))

    # Title
    story.append(Paragraph("SECOND NOTICE: RESTITUTION REBUTTAL & ESCALATION DEMAND", styles["doc_title"]))
    story.append(Paragraph(
        f"FLIGHT {flight.flight_number} — OPERATED BY {flight.airline}",
        styles["doc_subtitle"],
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 4))

    # Rebuttal letter content parsing (split by double newlines)
    paragraphs = rebuttal_text.strip().split("\n\n")
    for para in paragraphs:
        if para.strip():
            # If the paragraph is short and has bold tags or headers, style it appropriately
            clean_para = para.strip().replace("\n", "<br/>")
            story.append(Paragraph(clean_para, styles["body"]))
            story.append(Spacer(1, 3))

    # Add spacing and signature block placeholder if not present
    story.append(Spacer(1, 6))
    
    # Financial reference sub-table
    story.append(Paragraph("DESIGNATED ESCROW ACCOUNT DETAILS", styles["section_heading"]))
    payment_data = [
        ["Escrow Detail", "Value"],
        ["Escrow Holder", "Chexy Mock Ledger Network"],
        ["Routing / Transit Code", ledger.transit_routing],
        ["Account Identifier", f"****{ledger.account_number[-4:]}"],
        ["Total Amount Outstanding", f"{ledger.breakdown.total_claim:,.2f} {ledger.breakdown.total_claim_currency}"],
    ]
    payment_table = Table(payment_data, colWidths=[2.5 * inch, 4.3 * inch])
    payment_table.setStyle(_kv_table_style())
    story.append(KeepTogether([payment_table]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 3))
    
    # Sandbox disclaimer
    story.append(Paragraph(
        "⚠️  SANDBOX DISCLAIMER: This document was generated by an automated hackathon "
        "demonstration system. It does not constitute legal advice. No real money has been "
        "transferred. All banking details are synthetically generated. Built at Hack the 6ix "
        "2026 using OpenRouter AI, Stay22, and Chexy-inspired payment tracking.",
        styles["small"],
    ))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"Document generated: {today_str}  |  Rebuttal ID: {rebut_id}  |  Claim ID: {claim_id}",
        styles["small"],
    ))

    doc.build(story)
    logger.info(f"Rebuttal PDF generated: {output_path}")
    return str(output_path.resolve())

