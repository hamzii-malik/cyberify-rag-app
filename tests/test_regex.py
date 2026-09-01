"""
Test suite for Regex patterns, entity detection in documents, and /api/submit endpoint.
"""
import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output encoding if possible
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.main import (
    REGEX_PATTERNS_VALIDATION,
    REGEX_PATTERNS_EXTRACTION,
    detect_regex_entities,
)

def test_name_validation():
    pattern = REGEX_PATTERNS_VALIDATION["name"]
    valid_names = ["Hamza Ali", "Usman Tariq", "John Doe", "Dr. Sarah O'Connor", "Muhammad-Ali"]
    invalid_names = ["12345", "A", "@#$%", "", "a" * 70]

    for name in valid_names:
        assert re.match(pattern, name), f"Expected valid name: {name}"

    for name in invalid_names:
        assert not re.match(pattern, name), f"Expected invalid name: {name}"
    print("[PASS] Name Validation Regex tests passed")

def test_email_validation():
    pattern = REGEX_PATTERNS_VALIDATION["email"]
    valid_emails = ["hamza@cyberify.ai", "user.name+tag@example.co.uk", "admin_123@domain.org"]
    invalid_emails = ["plainaddress", "missing@domain", "@missinguser.com", "user@.com", "user@domain..com"]

    for email in valid_emails:
        assert re.match(pattern, email), f"Expected valid email: {email}"

    for email in invalid_emails:
        assert not re.match(pattern, email), f"Expected invalid email: {email}"
    print("[PASS] Email Validation Regex tests passed")

def test_phone_validation():
    pattern = REGEX_PATTERNS_VALIDATION["phone"]
    valid_phones = ["+92 300 1234567", "0300-1234567", "+1 (415) 555-0199", "03214455667", "+44 20 7946 0912"]
    invalid_phones = ["123", "abc-def-ghij", "++92300", ""]

    for phone in valid_phones:
        assert re.match(pattern, phone), f"Expected valid phone: {phone}"

    for phone in invalid_phones:
        assert not re.match(pattern, phone), f"Expected invalid phone: {phone}"
    print("[PASS] Phone Validation Regex tests passed")

def test_document_entity_extraction():
    sample_text = """
    PROJECT PROPOSAL & CONTACT DIRECTORY
    -----------------------------------------------------
    Client Representative: Sarah Johnson (sarah.j@techcorp.io, +1 415-555-0199)
    Lead Engineer: Usman Tariq (usman@cloudnet.pk, +92 321-4455667)
    Project Auditor: David Miller (dmiller@audit.org, +44 20 7946 0912)

    For emergency escalations, contact support@cyberify.ai or call 0300-9876543.
    """

    res = detect_regex_entities(sample_text)
    
    assert "Sarah Johnson" in res["names"]
    assert "Usman Tariq" in res["names"]
    assert "David Miller" in res["names"]

    assert "sarah.j@techcorp.io" in res["emails"]
    assert "usman@cloudnet.pk" in res["emails"]
    assert "dmiller@audit.org" in res["emails"]
    assert "support@cyberify.ai" in res["emails"]

    assert len(res["phones"]) >= 4
    assert res["total_detected"] >= 10

    print("[PASS] Document Entity Extraction Regex tests passed")

def test_fastapi_submit_endpoint():
    try:
        from fastapi.testclient import TestClient
        from app.main import api

        client = TestClient(api)

        # 1. Test Pattern list
        resp = client.get("/api/regex/patterns")
        assert resp.status_code == 200
        patterns = resp.json()
        assert "validation_patterns" in patterns
        assert "name" in patterns["validation_patterns"]

        # 2. Test Detect endpoint
        resp = client.post("/api/regex/detect", json={"text": "Contact Hamza Ali at hamza@example.com or +923001234567"})
        assert resp.status_code == 200
        data = resp.json()
        assert "Hamza Ali" in data["names"]
        assert "hamza@example.com" in data["emails"]

        # 3. Test Form Submit endpoint
        payload = {
            "name": "Hamza Ali",
            "email": "hamza@cyberify.ai",
            "phone": "+92 300 1234567",
            "document_text": "Lead Architect: Usman Tariq (usman@example.com, +92 321 9876543)",
            "notes": "Testing form submission",
            "create_onlyoffice_doc": True,
            "index_in_rag": False
        }
        resp = client.post("/api/submit", json=payload)
        assert resp.status_code == 200
        res = resp.json()
        assert res["status"] == "success"
        assert res["validation"]["name"]["valid"] is True
        assert res["validation"]["email"]["valid"] is True
        assert res["validation"]["phone"]["valid"] is True
        assert "editor.html" in res["redirect_url"]
        assert res["document_filename"] is not None

        # 4. Test Invalid Submission
        invalid_payload = {
            "name": "123",
            "email": "not-an-email",
            "phone": "abc",
            "document_text": "",
            "create_onlyoffice_doc": False
        }
        resp = client.post("/api/submit", json=invalid_payload)
        assert resp.status_code == 422

        print("[PASS] FastAPI Submit & Regex Endpoints tests passed")
    except ImportError as e:
        print(f"[SKIP] TestClient tests skipped: {e}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("RUNNING REGEX PATTERN & SUBMIT FORM TESTS")
    print("="*60)
    test_name_validation()
    test_email_validation()
    test_phone_validation()
    test_document_entity_extraction()
    test_fastapi_submit_endpoint()
    print("\n" + "="*60)
    print("ALL REGEX TESTS COMPLETED SUCCESSFULLY!")
    print("="*60 + "\n")
