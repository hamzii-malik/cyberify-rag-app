"""Regex patterns for detecting Name / Email / Phone Number inside text or
uploaded document files, plus simple validators used by the contact form.

Run this file directly (``python -m app.patterns``) to execute the built-in
self-tests and confirm every pattern still matches/rejects the expected
sample values.
"""

import re
from pathlib import Path

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

PHONE_PATTERN = re.compile(
    r"(?:\+92[\s-]?|0)3\d{2}[\s-]?\d{7}"
)

NAME_PATTERN = re.compile(
    r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2}\b"
)

NAME_FORM_PATTERN = re.compile(
    r"^[A-Za-z]+(?:[ \t.'-][A-Za-z]+)*$"
)


PLACEHOLDER_PATTERNS = {
    "name": re.compile(r"\{name\}", re.IGNORECASE),
    "email": re.compile(r"\[email\]", re.IGNORECASE),
    "contact": re.compile(r"\((?:contact|phone)\)", re.IGNORECASE),
}

PATTERNS = {
    "name": NAME_PATTERN,
    "email": EMAIL_PATTERN,
    "phone": PHONE_PATTERN,
}

FIELD_VALIDATORS = {
    "name": NAME_FORM_PATTERN,
    "email": EMAIL_PATTERN,
    "phone": PHONE_PATTERN,
}


def fill_template(template: str, name: str, email: str, phone: str) -> str:
    """Replace {name}, [email], and (contact)/(phone) in template text."""
    text = PLACEHOLDER_PATTERNS["name"].sub(name, template)
    text = PLACEHOLDER_PATTERNS["email"].sub(email, text)
    text = PLACEHOLDER_PATTERNS["contact"].sub(phone, text)
    return text


def create_contact_document(target_path: Path, name: str, email: str, phone: str) -> Path:
    """Create a clean, professional Word document (.docx) with contact details."""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from datetime import datetime

    doc = docx.Document()

    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    title = doc.add_heading("CYBERIFY", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in title.runs:
        run.font.size = Pt(22)
        run.font.bold = True
        run.font.color.rgb = RGBColor(99, 102, 241)  # Indigo/Purple

    subtitle = doc.add_paragraph("Official Contact & Client Registration Form")
    subtitle.paragraph_format.space_after = Pt(18)
    for run in subtitle.runs:
        run.font.size = Pt(13)
        run.font.color.rgb = RGBColor(100, 116, 139)

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.autofit = False

    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Field Description"
    hdr_cells[1].text = "Details"
    for cell in hdr_cells:
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(30, 41, 59)

    records = [
        ("Full Name", name),
        ("Email Address", email),
        ("Phone Number", phone),
        ("Registration Date", datetime.now().strftime("%B %d, %Y - %I:%M %p")),
    ]

    for label, val in records:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[0].paragraphs[0].runs[0].font.bold = True
        row_cells[1].text = val

    doc.add_paragraph("").paragraph_format.space_after = Pt(12)

    # Confirmation Message
    msg_heading = doc.add_heading("Confirmation & Acknowledgment", level=2)
    for run in msg_heading.runs:
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(30, 41, 59)

    template = (
        "Dear {name},\n\n"
        "Thank you for contacting Cyberify. We have successfully registered your contact inquiry.\n\n"
        "Our team will reach out to you directly at [email] or via phone at (contact).\n\n"
        "If any of the above information requires modification, you can edit this document directly inside OnlyOffice."
    )
    filled_letter = fill_template(template, name, email, phone)

    p_letter = doc.add_paragraph(filled_letter)
    p_letter.paragraph_format.line_spacing = 1.25
    p_letter.paragraph_format.space_after = Pt(20)

    p_sign = doc.add_paragraph("Sincerely,\nCyberify Communications Team\nwww.cyberify.io")
    for run in p_sign.runs:
        run.font.color.rgb = RGBColor(100, 116, 139)
        run.font.italic = True

    target_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target_path))
    return target_path

def detect_patterns(text: str) -> dict:
    """Run every regex pattern against `text` and return the matches found."""
    results = {}
    for label, pattern in PATTERNS.items():
        matches = sorted(set(m.strip() for m in pattern.findall(text)))
        results[label] = matches
    return results


def compare_patterns(text: str, first: str, second: str) -> dict:
    """Compare the matches produced by two registered patterns."""
    first_pattern = PATTERNS.get(first)
    second_pattern = PATTERNS.get(second)
    if first_pattern is None or second_pattern is None:
        raise ValueError("Patterns must be registered name, email, or phone")

    first_matches = set(m.strip() for m in first_pattern.findall(text))
    second_matches = set(m.strip() for m in second_pattern.findall(text))
    return {
        "first": first,
        "second": second,
        "common": sorted(first_matches & second_matches),
        "only_in_first": sorted(first_matches - second_matches),
        "only_in_second": sorted(second_matches - first_matches),
    }


def validate_field(field: str, value: str) -> bool:
    """True if `value` fully matches the pattern registered for `field`."""
    pattern = FIELD_VALIDATORS.get(field)
    if pattern is None:
        raise ValueError(f"Unknown field: {field}")
    val = value.strip()
    if not val:
        return False
    return bool(pattern.fullmatch(val))



def extract_text_from_file(path: Path) -> str:
    """Best-effort plain-text extraction for the file types we support."""
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        try:
            import docx  
        except ImportError as e:
            raise RuntimeError(
                "python-docx is required to read .docx files. "
                "Install it with: pip install python-docx"
            ) from e
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)

    raise ValueError(f"Unsupported file type for pattern detection: {suffix}")



def _run_self_tests() -> None:
    sample_text = """
    Contact Person: Ali Raza
    Email me at ali.raza@example.com or hr.team@cyberify.io
    Call on 03001234567 or +92 300 1234567 for queries.
    Backup contact: Sara Ahmed, sara_ahmed99@gmail.com, 0345-9876543
    """

    results = detect_patterns(sample_text)
    print("Detected names :", results["name"])
    print("Detected emails:", results["email"])
    print("Detected phones:", results["phone"])

    assert "Ali Raza" in results["name"], "Name pattern failed"
    assert "Sara Ahmed" in results["name"], "Name pattern failed"
    assert "ali.raza@example.com" in results["email"], "Email pattern failed"
    assert "hr.team@cyberify.io" in results["email"], "Email pattern failed"
    assert "03001234567" in results["phone"], "Phone pattern failed"
    assert "0345-9876543" in results["phone"], "Phone pattern failed"

    # Field validators (used by the submit-form endpoint)
    assert validate_field("email", "student@cyberify.io") is True
    assert validate_field("email", "not-an-email") is False
    assert validate_field("phone", "03211234567") is True
    assert validate_field("phone", "12345") is False
    assert validate_field("name", "Ahmed Khan") is True
    assert validate_field("name", "Hamza") is True
    assert validate_field("name", "1234") is False

    print("\nAll pattern self-tests passed [OK]")


if __name__ == "__main__":
    _run_self_tests()
