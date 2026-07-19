# ClaimFlight

> **Hack the 6ix 2026** — Automated passenger rights engine and statutory restitution pipeline for delayed or cancelled flights.

Paste a raw airline delay/cancellation email or upload a boarding pass image → ClaimFlight instantly calculates your statutory entitlement, generates a formal legal PDF demand letter, embeds a live Stay22 accommodation search for your stranded night, and establishes a Chexy-style synthetic payment ledger. 

If the airline rejects your claim, paste the rejection email into the **Dispute Rebuttal Engine** to generate a legally-worded Second Notice rebuttal letter targeting airline loop-holes.

---

## Features & Integration Tracks
- **Stay22 (Peak Unhinged Big Brain)** — Embeds a dynamic accommodation widget based on arrival city and disruption date, formatted as a "Mandatory Accommodation Relief" deep-link in legal demand letters.
- **Chexy (Make Every Payment Count)** — Generates a synthetic payment ledger tracking dispute state, complete with routing/account numbers and interactive claim reconciliation.
- **OpenRouter / Local Heuristics** — Dynamic routing using OpenRouter's free models with automatic local heuristic fallback to ensure 100% uptime even when upstream APIs are rate-limited.
- **Dispute Rebuttal Engine** — Scans airline rejection emails for weather or mechanical maintenance excuses and auto-generates a formal rebuttal citing case law and regulatory frameworks.

---

## Setup

### 1. Configure Environment Variables
Copy `.env.example` to `.env` and set your OpenRouter API key:
```env
Open_Router_KEY="your_openrouter_api_key_here"
```

### 2. Install Dependencies & Run
```bash
pip install -r requirements.txt
python run.py
```

### 3. Open the Web App
- **Dashboard UI:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## How It Works

```
Disruption Email / Boarding Pass Image
                │
                ▼
OpenRouter AI / Local parsing heuristics
                │   airline, flight, route, delay, cancellation, date
                ▼
Regulation Engine (ICAO prefix routing)
                │   CY* → Canada APPR s.19 ($1,000 CAD)
                │   ED*/LF*/EG* → EU 261/2004 (€600)
                │   Default → US DOT baseline
                ▼
Stay22 URL Builder
                │   live accommodation list & embed for arrival city
                ▼
ReportLab PDF Generator
                │   Formal 2-page "Demand for Statutory Restitution" PDF
                ▼
Chexy Payment Ledger
                │   Synthetic routing/account details & status tracking
                ▼
Dashboard Update & Claim Reconciler
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Responsive HTML dashboard |
| `GET` | `/api/health` | Service health status |
| `POST` | `/api/extort/extract` | Text extraction pipeline (Email to claim generation) |
| `POST` | `/api/extort/extract-image` | Multimodal extraction pipeline (Boarding pass image to claim) |
| `POST` | `/api/extort/rebut` | Dispute Rebuttal Engine (Rejection analysis to rebuttal letter) |
| `GET` | `/api/extort/pdf/{claim_id}` | Download generated demand/rebuttal PDF |
| `POST` | `/api/extort/reconcile` | View/update claim status in ledger |
| `GET` | `/api/extort/ledger` | List all synthetic ledger entries |

---

## Testing

Verify the end-to-end extraction, regulation engine, PDF generator, and status updates:
```bash
python test_extract.py
```

---

## Regulation Coverage

| Jurisdiction | Regulation | Trigger | Max Entitlement |
|---|---|---|---|
| **Canada** | APPR Section 19 | ≥9h delay | $1,000 CAD |
| **Canada** | APPR Section 19 | 6h - 9h delay | $700 CAD |
| **Canada** | APPR Section 19 | 3h - 6h delay | $400 CAD |
| **Europe** | EU Reg 261/2004 | >3h delay (long-haul) | €600 |
| **Europe** | EU Reg 261/2004 | >3h delay (medium) | €400 |
| **Europe** | EU Reg 261/2004 | >3h delay (short) | €250 |
| **USA** | US DOT | Involuntary Denied Boarding | $1,550 USD |

---

> **Disclaimer:** ClaimFlight is a hackathon demonstration prototype. It does not constitute legal advice. All bank transfer actions are synthetic sandbox simulations. Built at Hack the 6ix 2026.
