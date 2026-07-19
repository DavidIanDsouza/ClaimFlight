"""
app/main.py — FastAPI application for The Flight Delay Extorter

Endpoints:
  GET  /                          → Dark-mode HTML dashboard
  GET  /api/health                → Health check
  POST /api/extort/extract        → Full pipeline (OpenRouter → regulation → Stay22 → PDF → ledger)
  GET  /api/extort/pdf/{claim_id} → Download generated demand letter PDF
  POST /api/extort/reconcile      → View/update mock payment ledger entry
  GET  /api/extort/ledger         → List all synthetic ledger entries
"""
from __future__ import annotations

import uuid
import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.models import (
    ExtractRequest,
    ReconcileRequest,
    ClaimResult,
    LedgerEntry,
    RebutRequest,
    RebutResponse,
    FlightDetails,
)

from app.openrouter_extractor import (
    extract_flight_details,
    extract_flight_details_from_image,
    analyze_rejection_and_generate_rebuttal,
)
from app.regulation_engine import calculate_entitlement
from app.stay22_utils import build_stay22_embed_url, build_stay22_list_url
from app.pdf_generator import (
    generate_demand_pdf,
    generate_rebuttal_pdf,
    PDF_OUTPUT_DIR,
)
from app.payment_ledger import (
    create_ledger_entry,
    get_ledger_entry,
    update_ledger_status,
    list_all_entries,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="✈️ ClaimFlight",
    description=(
        "Automated legal discovery and restitution tool for flight delay/cancellation passengers. "
        "Paste an airline email → get jurisdiction-aware entitlement (APPR/EU261/US DOT), "
        "a formal PDF demand letter, Stay22 accommodation search, and a Chexy-style payment ledger."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Hack the 6ix 2026",
        "url": "https://hackthe6ix.com",
    },
    license_info={
        "name": "MIT",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Dashboard HTML (served from app/dashboard.html)
# ---------------------------------------------------------------------------
_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"
_WORKSPACE_DIR = Path(__file__).parent.parent
_LOGO_LIGHT_PATH = _WORKSPACE_DIR / "ClaimFlight.png"
_LOGO_DARK_PATH = _WORKSPACE_DIR / "ClaimFlightDark.png"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    """Serve the dark-mode single-page HTML dashboard."""
    if _DASHBOARD_PATH.exists():
        return HTMLResponse(content=_DASHBOARD_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Dashboard not found. Use /docs for API testing.</h1>",
        status_code=200,
    )


@app.get("/ClaimFlight.png", include_in_schema=False)
async def get_logo_light():
    """Serve light logo."""
    if _LOGO_LIGHT_PATH.exists():
        return FileResponse(_LOGO_LIGHT_PATH, media_type="image/png")
    raise HTTPException(status_code=404, detail="Light logo not found")


@app.get("/ClaimFlightDark.png", include_in_schema=False)
async def get_logo_dark():
    """Serve dark logo."""
    if _LOGO_DARK_PATH.exists():
        return FileResponse(_LOGO_DARK_PATH, media_type="image/png")
    raise HTTPException(status_code=404, detail="Dark logo not found")


@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon():
    """Serve favicon.ico using dark logo (since theme is dark mode)."""
    if _LOGO_DARK_PATH.exists():
        return FileResponse(_LOGO_DARK_PATH, media_type="image/png")
    elif _LOGO_LIGHT_PATH.exists():
        return FileResponse(_LOGO_LIGHT_PATH, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["System"])
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "ClaimFlight",
        "version": "1.0.0",
        "openrouter_model": "openrouter/free",
        "stay22_aid": "hackthe6ix2026",
    }


# ---------------------------------------------------------------------------
# Step 1-5: Main extraction + full pipeline
# ---------------------------------------------------------------------------
@app.post(
    "/api/extort/extract",
    response_model=ClaimResult,
    summary="Extract flight details and generate statutory claim",
    tags=["Extortion Engine"],
)
async def extract_and_claim(request: ExtractRequest):
    """
    **The main endpoint.** Full 5-step pipeline:
 
    1. **OpenRouter API** — Extract structured flight details from raw email text
    2. **Regulation Engine** — Route by ICAO prefix → APPR / EU261 / US DOT entitlement
    3. **Stay22** — Generate hotel search iframe + booking deep-link for arrival city
    4. **ReportLab PDF** — Generate formal "Demand for Statutory Restitution" letter
    5. **Chexy Ledger** — Create synthetic payment ledger entry with claim breakdown
 
    Returns a `ClaimResult` with all data + `pdf_download_url` + `stay22_embed_url`.
    """
    claim_id = f"FDE-{uuid.uuid4().hex[:10].upper()}"
    logger.info(f"[{claim_id}] New extraction request received.")
 
    # ----- Step 1: OpenRouter extraction (with automatic local fallback on quota/API limits) -----
    try:
        flight, source = extract_flight_details(request.email_text)
    except Exception as e:
        logger.error(f"[{claim_id}] Both OpenRouter and Fallback extraction failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract flight details from the provided text: {str(e)}",
        )
 
    # ----- Step 2: Regulation engine -----
    entitlement = calculate_entitlement(flight)
    logger.info(f"[{claim_id}] Entitlement: {entitlement.entitlement_amount} {entitlement.entitlement_currency}")
 
    # ----- Step 3: Stay22 URLs -----
    stay22_embed = build_stay22_embed_url(
        city=flight.arrival_city,
        checkin_date=flight.original_departure_date,
    )
    stay22_list = build_stay22_list_url(
        city=flight.arrival_city,
        checkin_date=flight.original_departure_date,
    )
    logger.info(f"[{claim_id}] Stay22 URL: {stay22_embed}")
 
    # ----- Step 4: PDF generation -----
    try:
        # First create ledger entry (needed by PDF)
        ledger_entry = create_ledger_entry(claim_id, flight, entitlement)
 
        pdf_path = generate_demand_pdf(
            claim_id=claim_id,
            flight=flight,
            entitlement=entitlement,
            ledger=ledger_entry,
            stay22_list_url=stay22_list,
            stay22_embed_url=stay22_embed,
        )
        logger.info(f"[{claim_id}] PDF generated: {pdf_path}")
    except Exception as e:
        logger.error(f"[{claim_id}] PDF generation failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}",
        )
 
    pdf_download_url = f"/api/extort/pdf/{claim_id}"
 
    # Build response message
    if source == "Local Heuristic Fallback":
        msg = (
            f"Statutory restitution claim generated. [NOTICE: OpenRouter API rate limit/quota reached. "
            f"Used local heuristic fallback parser.] You are entitled to "
            f"{entitlement.entitlement_amount:,.0f} {entitlement.entitlement_currency} "
            f"under {entitlement.regulation_name}."
        )
    else:
        msg = (
            f"Statutory restitution claim generated. [Source: OpenRouter (free)] "
            f"You are entitled to {entitlement.entitlement_amount:,.0f} "
            f"{entitlement.entitlement_currency} under {entitlement.regulation_name}."
        )
 
    return ClaimResult(
        claim_id=claim_id,
        flight_details=flight,
        entitlement=entitlement,
        stay22_embed_url=stay22_embed,
        stay22_list_url=stay22_list,
        pdf_download_url=pdf_download_url,
        ledger_entry=ledger_entry,
        message=msg,
        extraction_source=source,
    )




# ---------------------------------------------------------------------------
# Multimodal Image extraction route
# ---------------------------------------------------------------------------
@app.post(
    "/api/extort/extract-image",
    response_model=ClaimResult,
    summary="Extract flight details from boarding pass/ticket image",
    tags=["Extortion Engine"],
)
async def extract_image_and_claim(file: UploadFile = File(...)):
    """
    **Multimodal image parsing endpoint.**

    Accepts an uploaded image file (ticket screenshot or boarding pass), extracts flight
    details using OpenRouter Multimodal parsing, routes through jurisdiction logic, builds Stay22 URL,
    generates demand PDF, and logs in Chexy mock ledger.
    """
    claim_id = f"FDE-IMG-{uuid.uuid4().hex[:8].upper()}"
    logger.info(f"[{claim_id}] New image extraction request: {file.filename} ({file.content_type})")

    # Read image bytes
    image_bytes = await file.read()
    mime_type = file.content_type or "image/png"

    # ----- Step 1: Multimodal Extraction -----
    try:
        flight, source = extract_flight_details_from_image(image_bytes, mime_type)
    except Exception as e:
        logger.error(f"[{claim_id}] Multimodal extraction failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract details from image: {str(e)}",
        )

    # ----- Step 2: Regulation engine -----
    entitlement = calculate_entitlement(flight)
    logger.info(f"[{claim_id}] Entitlement: {entitlement.entitlement_amount} {entitlement.entitlement_currency}")

    # ----- Step 3: Stay22 URLs -----
    stay22_embed = build_stay22_embed_url(
        city=flight.arrival_city,
        checkin_date=flight.original_departure_date,
    )
    stay22_list = build_stay22_list_url(
        city=flight.arrival_city,
        checkin_date=flight.original_departure_date,
    )

    # ----- Step 4: PDF generation -----
    try:
        ledger_entry = create_ledger_entry(claim_id, flight, entitlement)
        pdf_path = generate_demand_pdf(
            claim_id=claim_id,
            flight=flight,
            entitlement=entitlement,
            ledger=ledger_entry,
            stay22_list_url=stay22_list,
            stay22_embed_url=stay22_embed,
        )
    except Exception as e:
        logger.error(f"[{claim_id}] PDF generation failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}",
        )

    pdf_download_url = f"/api/extort/pdf/{claim_id}"

    # Build response message
    if "Fallback" in source:
        msg = f"Statutory claim generated via fallback parser due to OpenRouter quota restrictions."
    else:
        msg = f"Statutory claim generated successfully using OpenRouter Multimodal image extraction."

    return ClaimResult(
        claim_id=claim_id,
        flight_details=flight,
        entitlement=entitlement,
        stay22_embed_url=stay22_embed,
        stay22_list_url=stay22_list,
        pdf_download_url=pdf_download_url,
        ledger_entry=ledger_entry,
        message=msg,
        extraction_source=source,
    )


# ---------------------------------------------------------------------------
# Rebuttal Analysis & Escalation Letter (BS Detector)
# ---------------------------------------------------------------------------
@app.post(
    "/api/extort/rebut",
    response_model=RebutResponse,
    summary="Analyze airline rejection letter and generate escalation rebuttal",
    tags=["Restitution Arbitration"],
)
async def rebut_rejection(request: RebutRequest):
    """
    **The Rebuttal BS Detector Endpoint.**

    Takes an airline's rejection email, analyzes it for loopholes,
    automatically marks the ledger dispute status to 'DISPUTED',
    and generates a formal 'Second Notice Escalation & Rebuttal' PDF letter.
    """
    claim_id = request.original_claim_id.strip()
    rebut_id = f"REBUT-{uuid.uuid4().hex[:8].upper()}"
    logger.info(f"[{rebut_id}] Rebuttal request for claim {claim_id}")

    # Fetch original ledger entry
    ledger = get_ledger_entry(claim_id)
    if ledger is None:
        raise HTTPException(
            status_code=404,
            detail=f"Original claim ID '{claim_id}' not found in ledger. Rebuttal requires an active claim.",
        )

    # Force update the ledger status to DISPUTED (simulating Chexy payment dispute reconciliation)
    update_ledger_status(claim_id, "DISPUTED")

    # Reconstruct flight info for prompt
    flight = FlightDetails(
        airline=ledger.airline,
        flight_number=ledger.flight_number,
        departure_airport=ledger.notes.split("Delay:")[0].split("from ")[-1].split(" to ")[0].strip() if "from " in ledger.notes else "CYYZ",
        arrival_airport=ledger.notes.split("Delay:")[0].split(" to ")[-1].split(" ")[0].strip() if " to " in ledger.notes else "CYVR",
        arrival_city=ledger.notes.split("Delay:")[0].split(" to ")[-1].split(" ")[0].strip() if " to " in ledger.notes else "Vancouver",
        delay_duration_hours=float(ledger.notes.split("Delay:")[1].split("h")[0].strip()) if "Delay:" in ledger.notes else 6.0,
        original_departure_date=ledger.notes.split("on ")[1].split(".")[0].strip() if "on " in ledger.notes else "2026-07-20",
        cancellation="cancelled" in ledger.notes.lower() or "cancellation" in ledger.notes.lower(),
    )

    # Mock dynamic entitlement result based on ledger currency
    entitlement = calculate_entitlement(flight)

    # ----- Run Analysis & Rebuttal prompt -----
    try:
        loophole_analysis, rebuttal_letter = analyze_rejection_and_generate_rebuttal(
            rejection_text=request.rejection_text,
            flight=flight,
            entitlement=entitlement,
        )
    except Exception as e:
        logger.error(f"[{rebut_id}] Rebuttal parsing failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Rebuttal generation failed: {str(e)}",
        )

    # ----- Generate Rebuttal PDF -----
    try:
        # Fetch updated ledger entry
        updated_ledger = get_ledger_entry(claim_id)
        generate_rebuttal_pdf(
            rebut_id=rebut_id,
            claim_id=claim_id,
            flight=flight,
            rebuttal_text=rebuttal_letter,
            ledger=updated_ledger,
        )
    except Exception as e:
        logger.error(f"[{rebut_id}] Rebuttal PDF generation failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Rebuttal PDF generation failed: {str(e)}",
        )

    pdf_download_url = f"/api/extort/pdf-rebuttal/{rebut_id}"

    return RebutResponse(
        claim_id=claim_id,
        rebut_id=rebut_id,
        loophole_analysis=loophole_analysis,
        rebuttal_letter=rebuttal_letter,
        pdf_download_url=pdf_download_url,
        original_ledger_entry=updated_ledger,
        message="Rebuttal analyzed. Ledger status escalated to DISPUTED.",
    )


# ---------------------------------------------------------------------------
# Serving Rebuttal PDFs
# ---------------------------------------------------------------------------
@app.get(
    "/api/extort/pdf-rebuttal/{rebut_id}",
    summary="Download rebuttal letter PDF",
    tags=["Restitution Arbitration"],
    response_class=FileResponse,
)
async def download_rebuttal_pdf(rebut_id: str):
    """Download the generated Second Notice Rebuttal PDF for a given rebuttal ID."""
    pdf_path = PDF_OUTPUT_DIR / f"{rebut_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No PDF found for rebuttal ID '{rebut_id}'.",
        )
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"Second_Notice_Escalation_{rebut_id}.pdf",
    )


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------
@app.get(
    "/api/extort/pdf/{claim_id}",
    summary="Download demand letter PDF",
    tags=["Extortion Engine"],
    response_class=FileResponse,
)
async def download_pdf(claim_id: str):
    """Download the generated Demand for Statutory Restitution PDF for a given claim ID."""
    pdf_path = PDF_OUTPUT_DIR / f"{claim_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No PDF found for claim ID '{claim_id}'. Run /api/extort/extract first.",
        )
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"Demand_Letter_{claim_id}.pdf",
    )



# ---------------------------------------------------------------------------
# Chexy-style payment reconciliation
# ---------------------------------------------------------------------------
@app.post(
    "/api/extort/reconcile",
    response_model=LedgerEntry,
    summary="View or update a payment ledger entry (mock Chexy reconciliation)",
    tags=["Payment Ledger"],
)
async def reconcile_claim(request: ReconcileRequest):
    """
    **Mock Chexy reconciliation endpoint.**

    Retrieves a synthetic payment ledger entry by `claim_id`.
    Optionally updates the status (e.g. DISPUTED, SETTLED, CLOSED).

    This simulates a Chexy-style payment tracking workflow:
    - View account routing/transit details
    - See itemized claim breakdown
    - Update dispute status flags
    """
    entry = get_ledger_entry(request.claim_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ledger entry '{request.claim_id}' not found. Call /api/extort/extract first.",
        )

    if request.new_status:
        entry = update_ledger_status(request.claim_id, request.new_status)

    return entry


# ---------------------------------------------------------------------------
# Ledger list
# ---------------------------------------------------------------------------
@app.get(
    "/api/extort/ledger",
    response_model=list[LedgerEntry],
    summary="List all synthetic payment ledger entries",
    tags=["Payment Ledger"],
)
async def list_ledger():
    """
    Returns all in-memory payment ledger entries, newest first.
    Resets when the server restarts (intentional — demo/sandbox only).
    """
    return list_all_entries()


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "hint": "Check server logs for full traceback.",
        },
    )
