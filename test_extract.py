"""
test_extract.py — Smoke test / verification script for ClaimFlight

Run with: python test_extract.py
Requires: server running at http://localhost:8000 (run `python run.py` first)
"""
import sys
import json
import urllib.request
import urllib.error
import io

# Force UTF-8 encoding on Windows to prevent UnicodeEncodeError when printing emojis
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


BASE_URL = "http://localhost:8000"

# ── Test cases ────────────────────────────────────────────────────────────────
TEST_CASES = [
    {
        "name": "🇨🇦 Canada APPR — Air Canada 10h delay",
        "expected_jurisdiction": "Canada",
        "expected_currency": "CAD",
        "email_text": (
            "Dear valued passenger, Air Canada flight AC123 from Toronto Pearson "
            "International Airport (CYYZ) to Vancouver International Airport (CYVR) "
            "on July 20, 2026 has been delayed by 10 hours due to operational disruption "
            "caused by crew scheduling issues within our control. We sincerely apologize."
        ),
    },
    {
        "name": "🇪🇺 Europe EU261 — Lufthansa cancellation",
        "expected_jurisdiction": "Europe",
        "expected_currency": "EUR",
        "email_text": (
            "Dear Passenger, Lufthansa flight LH1234 departing from Frankfurt Airport (EDDF) "
            "to London Heathrow (EGLL) on August 15, 2026 has been CANCELLED due to an air "
            "traffic control strike. We will rebook you on the next available flight."
        ),
    },
    {
        "name": "🇺🇸 USA DOT — Delta 7h delay",
        "expected_jurisdiction": "USA",
        "expected_currency": "USD",
        "email_text": (
            "Dear Delta SkyMiles Member, Delta Air Lines flight DL456 from "
            "Hartsfield-Jackson Atlanta International Airport (KATL) to Los Angeles "
            "International Airport (KLAX) on August 5, 2026 has been delayed by 7 hours "
            "due to mechanical issues. Your original departure was 9:00 AM."
        ),
    },
]


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _get_json(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def test_health():
    print("\n── Health Check ──────────────────────────────────────────")
    try:
        data = _get_json(f"{BASE_URL}/api/health")
        assert data["status"] == "ok", f"Unexpected health status: {data}"
        print(f"  ✅ Health OK — {data['service']} v{data['version']}")
        print(f"     Model: {data['openrouter_model']} | Stay22 AID: {data['stay22_aid']}")
        return True
    except Exception as e:
        print(f"  ❌ Health check failed: {e}")
        print("     Is the server running? Start with: python run.py")
        return False


def test_extraction(case: dict) -> bool:
    print(f"\n── {case['name']} ──────────────────────────────────────")
    try:
        result = _post_json(
            f"{BASE_URL}/api/extort/extract",
            {"email_text": case["email_text"]},
        )

        claim_id = result["claim_id"]
        ent = result["entitlement"]
        flight = result["flight_details"]
        ledger = result["ledger_entry"]

        print(f"  ✅ Claim ID:     {claim_id}")
        print(f"     Flight:       {flight['airline']} {flight['flight_number']}")
        print(f"     Route:        {flight['departure_airport']} → {flight['arrival_airport']}")
        print(f"     Delay:        {flight['delay_duration_hours']}h | Cancelled: {flight['cancellation']}")
        print(f"     Jurisdiction: {ent['jurisdiction']}")
        print(f"     Entitlement:  {ent['entitlement_amount']:,.0f} {ent['entitlement_currency']}")
        print(f"     Total Claim:  {ledger['breakdown']['total_claim']:,.2f} {ledger['breakdown']['total_claim_currency']}")
        print(f"     Stay22 URL:   {result['stay22_embed_url'][:60]}...")
        print(f"     PDF URL:      {result['pdf_download_url']}")
        print(f"     Ledger Status:{ledger['status']}")
        print(f"     Routing #:    {ledger['transit_routing']}")

        # Assertions
        assert case["expected_jurisdiction"] in ent["jurisdiction"], (
            f"Expected jurisdiction {case['expected_jurisdiction']} but got {ent['jurisdiction']}"
        )
        assert ent["entitlement_currency"] == case["expected_currency"], (
            f"Expected currency {case['expected_currency']} but got {ent['entitlement_currency']}"
        )
        assert result["stay22_embed_url"].startswith("https://www.stay22.com"), "Bad Stay22 URL"
        assert "hackthe6ix2026" in result["stay22_embed_url"], "Missing Stay22 affiliate ID"
        assert result["pdf_download_url"].startswith("/api/extort/pdf/"), "Bad PDF URL"
        assert ledger["status"] == "PENDING_DISPUTE_RESPONSE", f"Unexpected ledger status: {ledger['status']}"

        return claim_id
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


def test_reconcile(claim_id: str) -> bool:
    print(f"\n── Reconcile Test — {claim_id} ──────────────────────────")
    try:
        result = _post_json(
            f"{BASE_URL}/api/extort/reconcile",
            {"claim_id": claim_id, "new_status": "DISPUTED"},
        )
        assert result["status"] == "DISPUTED", f"Expected DISPUTED, got {result['status']}"
        print(f"  ✅ Status updated to: {result['status']}")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False


def test_ledger() -> bool:
    print(f"\n── Ledger List Test ──────────────────────────────────────")
    try:
        entries = _get_json(f"{BASE_URL}/api/extort/ledger")
        print(f"  ✅ Ledger has {len(entries)} entries")
        return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False


def main():
    print("=" * 60)
    print("  ✈️  ClaimFlight — Smoke Tests")
    print("=" * 60)

    # Health check
    if not test_health():
        sys.exit(1)

    # Extraction tests
    claim_ids = []
    for case in TEST_CASES:
        cid = test_extraction(case)
        if cid:
            claim_ids.append(cid)

    # Reconcile test (use first successful claim)
    if claim_ids:
        test_reconcile(claim_ids[0])

    # Ledger test
    test_ledger()

    # Summary
    passed = len(claim_ids)
    total = len(TEST_CASES)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} extraction tests passed")
    if passed == total:
        print("  🎉 All tests passed!")
    else:
        print("  ⚠️  Some tests failed. Check GOOGLE_API_KEY and server logs.")
    print("=" * 60)

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
