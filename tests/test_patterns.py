"""Tests for app/patterns.py — the Name / Email / Phone regex patterns used
by the contact form (validation) and the document pattern-detector."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import patterns


SAMPLE_DOC_TEXT = """
Contact Person: Ali Raza
Email me at ali.raza@example.com or hr.team@cyberify.io
Call on 03001234567 or +92 300 1234567 for queries.
Backup contact: Sara Ahmed, sara_ahmed99@gmail.com, 0345-9876543
Not a match: 12345, plainword, someone@nodot
"""


def test_detect_names():
    found = patterns.detect_patterns(SAMPLE_DOC_TEXT)["name"]
    assert "Ali Raza" in found
    assert "Sara Ahmed" in found


def test_detect_emails():
    found = patterns.detect_patterns(SAMPLE_DOC_TEXT)["email"]
    assert "ali.raza@example.com" in found
    assert "hr.team@cyberify.io" in found
    assert "sara_ahmed99@gmail.com" in found
    assert not any("nodot" in e for e in found)


def test_detect_phones():
    found = patterns.detect_patterns(SAMPLE_DOC_TEXT)["phone"]
    assert "03001234567" in found
    assert "0345-9876543" in found


def test_compare_patterns():
    result = patterns.compare_patterns(
        "Ali Raza ali@example.com 03001234567", "name", "email"
    )
    assert result["common"] == []
    assert result["only_in_first"] == ["Ali Raza"]
    assert result["only_in_second"] == ["ali@example.com"]


def test_compare_patterns_rejects_unknown_pattern():
    try:
        patterns.compare_patterns("sample", "name", "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown pattern should raise ValueError")


def test_validate_name():
    assert patterns.validate_field("name", "Ahmed Khan") is True
    assert patterns.validate_field("name", "ahmed") is True         # same as the contact form
    assert patterns.validate_field("name", "Ahmed123") is False     # digits not allowed
    assert patterns.validate_field("name", "") is False


def test_validate_email():
    assert patterns.validate_field("email", "student@cyberify.io") is True
    assert patterns.validate_field("email", "not-an-email") is False
    assert patterns.validate_field("email", "missing@dot") is False


def test_validate_phone():
    assert patterns.validate_field("phone", "03211234567") is True
    assert patterns.validate_field("phone", "0321-1234567") is True
    assert patterns.validate_field("phone", "+923211234567") is True
    assert patterns.validate_field("phone", "12345") is False
    assert patterns.validate_field("phone", "02211234567") is False  # not a mobile prefix


def test_extract_cv_fields():
    fields = patterns.extract_cv_fields(
        "Ali Raza\nEmail: ali@example.com\nSkills: Python, FastAPI\n"
        "Education\nBS Computer Science"
    )
    by_key = {field["key"]: field for field in fields}
    assert by_key["email"]["value"] == "ali@example.com"
    assert by_key["skills"]["value"] == "Python, FastAPI"
    assert by_key["email"]["validator"] == "email"
    assert "@" in by_key["email"]["regex"]
    assert by_key["skills"]["validator"] is None
    assert by_key["education"]["type"] == "textarea"


def test_validate_cv_fields_uses_contact_patterns():
    errors = patterns.validate_cv_fields([
        {"label": "Full Name", "key": "full_name", "value": "Ahmed Khan", "type": "text"},
        {"label": "Email", "key": "email", "value": "not-an-email", "type": "email"},
        {"label": "Skills", "key": "skills", "value": "Python", "type": "textarea"},
    ])
    assert errors == [{"label": "Email", "validator": "email"}]
    assert patterns.validate_cv_fields([
        {"label": "Email", "value": "ali@example.com", "type": "email"},
        {"label": "Phone", "value": "03001234567", "type": "tel"},
    ]) == []


if __name__ == "__main__":
    # Allow `python tests/test_patterns.py` without pytest installed.
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
