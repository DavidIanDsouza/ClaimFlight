"""
test_advanced.py — Smoke test for the Flight Delay Extorter's Advanced Features
- Multimodal Image Boarding Pass Parsing (with fallback)
- Rejection Rebuttal Engine / BS Detector (with fallback)

Run with: python test_advanced.py
Requires: server running at http://localhost:8000
"""
import sys
import json
import urllib.request
import urllib.error
import io

BASE_URL = "http://localhost:8000"

# Force UTF-8 on Windows terminal
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


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


def _post_multipart(url: str, filename: str, content_type: str, file_bytes: bytes) -> dict:
    boundary = "----WebKitFormBoundaryHackThe6ix2026"
    CRLF = b"\r\n"
    
    parts = []
    parts.append(f"--{boundary}".encode("utf-8"))
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"))
    parts.append(f"Content-Type: {content_type}".encode("utf-8"))
    parts.append(b"")
    parts.append(file_bytes)
    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")
    
    body = CRLF.join(parts)
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body))
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def test_health() -> bool:
    print("\n── Health Check ──────────────────────────────────────────")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"  [OK] Health OK — {data['service']} v{data['version']}")
            return True
    except Exception as e:
        print(f"  [FAIL] Server is not running: {e}")
        return False


def test_image_extraction() -> bool:
    print("\n── Multimodal Image Extraction Test ────────────────────────")
    # 1x1 pixel black PNG bytes
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc```"
        b"\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    try:
        result = _post_multipart(
            f"{BASE_URL}/api/extort/extract-image",
            "boarding_pass.png",
            "image/png",
            png_bytes
        )
        claim_id = result["claim_id"]
        flight = result["flight_details"]
        ent = result["entitlement"]
        source = result["extraction_source"]
        
        print(f"  [OK] Claim generated from image!")
        print(f"       Claim ID:          {claim_id}")
        print(f"       Airline:           {flight['airline']} ({flight['flight_number']})")
        print(f"       Jurisdiction:      {ent['jurisdiction']}")
        print(f"       Extraction Engine: {source}")
        
        assert claim_id.startswith("FDE-IMG-"), "Incorrect claim ID format"
        return claim_id
    except Exception as e:
        print(f"  [FAIL] Image extraction test failed: {e}")
        return None


def test_rebuttal(claim_id: str) -> bool:
    print("\n── Rejection Rebuttal (BS Detector) Test ──────────────────")
    rejection_text = (
        "Dear passenger, we have reviewed your request FDE-12345. "
        "Unfortunately, we must deny compensation because the delay was caused "
        "by severe winter weather at Toronto Pearson Airport, which is an "
        "extraordinary safety circumstance outside of WestJet control."
    )
    
    try:
        result = _post_json(
            f"{BASE_URL}/api/extort/rebut",
            {
                "original_claim_id": claim_id,
                "rejection_text": rejection_text
            }
        )
        rebut_id = result["rebut_id"]
        analysis = result["loophole_analysis"]
        letter = result["rebuttal_letter"]
        ledger = result["original_ledger_entry"]
        
        print(f"  [OK] Rebuttal generated!")
        print(f"       Rebuttal ID:       {rebut_id}")
        print(f"       New Ledger Status: {ledger['status']}")
        print(f"       Rebuttal PDF URL:  {result['pdf_download_url']}")
        print("\n  --- Loophole Analysis Snippet ---")
        print(analysis[:250].strip() + "...\n")
        
        assert rebut_id.startswith("REBUT-"), "Incorrect rebuttal ID format"
        assert ledger["status"] == "DISPUTED", "Ledger status was not updated to DISPUTED"
        return True
    except Exception as e:
        print(f"  [FAIL] Rebuttal test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  ✈️  ClaimFlight — Advanced Features Test")
    print("=" * 60)
    
    if not test_health():
        sys.exit(1)
        
    claim_id = test_image_extraction()
    if claim_id:
        test_rebuttal(claim_id)
        
    print("=" * 60)


if __name__ == "__main__":
    main()
