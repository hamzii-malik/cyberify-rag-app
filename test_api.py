#!/usr/bin/env python3
"""Test the RAG API endpoints."""

import requests
import json

BASE_URL = "http://localhost:8010"

print("\n" + "="*60)
print("🧪 RAG API TESTS")
print("="*60)

# Test 1: Health Check
print("\n✅ TEST 1: Health Check")
try:
    resp = requests.get(f"{BASE_URL}/api/health")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: List Documents
print("\n✅ TEST 2: List Documents")
try:
    resp = requests.get(f"{BASE_URL}/api/documents")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Ingest a Sample Document
print("\n✅ TEST 3: Ingest Sample Document")
try:
    payload = {
        "title": "Test Document",
        "source": "test_source",
        "text": "This is a test document. The company offers refunds within 30 days. Customer support is available 24/7."
    }
    resp = requests.post(f"{BASE_URL}/api/ingest", json=payload)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
    doc_id = data.get("document_id") if resp.status_code == 200 else None
except Exception as e:
    print(f"❌ Error: {e}")
    doc_id = None

# Test 4: Ask a Question
print("\n✅ TEST 4: Ask Question")
try:
    payload = {
        "question": "What is the refund policy?",
        "top_k": 3
    }
    resp = requests.post(f"{BASE_URL}/api/ask", json=payload)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"❌ Error: {e}")

# Test 5: List Documents Again
print("\n✅ TEST 5: List Documents After Ingestion")
try:
    resp = requests.get(f"{BASE_URL}/api/documents")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"❌ Error: {e}")

# Test 6: Regex Patterns & Definitions
print("\n[TEST 6] Get Regex Patterns")
try:
    resp = requests.get(f"{BASE_URL}/api/regex/patterns")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")

# Test 7: Regex Entity Detection in Document Text
print("\n[TEST 7] Detect Regex Entities in Document Text")
try:
    sample_text = (
        "Client Representative: Sarah Johnson (sarah.j@techcorp.io, +1 415-555-0199)\n"
        "Lead Engineer: Usman Tariq (usman@cloudnet.pk, +92 321-4455667)"
    )
    resp = requests.post(f"{BASE_URL}/api/regex/detect", json={"text": sample_text})
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")

# Test 8: Form Submission with Regex Validation & OnlyOffice Document Generation
print("\n[TEST 8] Form Submission & OnlyOffice Doc Generation")
try:
    form_payload = {
        "name": "Hamza Ali",
        "email": "hamza@cyberify.ai",
        "phone": "+92 300 1234567",
        "document_text": "Manager: David Miller (dmiller@cyberaudit.org, +44 20 7946 0912)",
        "notes": "Verified client submission",
        "create_onlyoffice_doc": True,
        "index_in_rag": False
    }
    resp = requests.post(f"{BASE_URL}/api/submit", json=form_payload)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*60)
print("✨ Tests Complete!")
print("="*60 + "\n")

