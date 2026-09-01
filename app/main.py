"""FastAPI app: Cyberify RAG Chatbot + OnlyOffice Document Integration + Regex Form & Document Scanner."""

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, ingest, rag
from app.config import CHAT_MODEL, EMBEDDING_MODEL, TOP_K

# Create uploads directory
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)

ONLYOFFICE_URL = os.getenv("ONLYOFFICE_URL", "http://localhost")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8010")
INTERNAL_BASE_URL = os.getenv("INTERNAL_BASE_URL", APP_BASE_URL)

api = FastAPI(title="Cyberify RAG & OnlyOffice Platform", version="2.0")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 1. REGEX PATTERNS DEFINITIONS
# ============================================================

# Regex Patterns for Form Validation (Field level)
REGEX_PATTERNS_VALIDATION = {
    "name": r"^[A-Za-z\s\.\-']{2,60}$",
    "email": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$",
    "phone": r"^(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}$"
}

# Regex Patterns for Document Entity Extraction (Text level)
REGEX_PATTERNS_EXTRACTION = {
    "name": r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",
    "email": r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}\b",
    "phone": r"(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b"
}

COMMON_NON_NAME_WORDS = {
    "Contact", "Please", "Hello", "Dear", "From", "To", "Representative",
    "Client", "Project", "Lead", "Senior", "Officer", "The", "This", "Our", "Date", "Phone", "Email"
}


def detect_regex_entities(text: str) -> dict:
    """Scan document or plain text and extract all regex pattern matches."""
    if not text:
        return {"names": [], "emails": [], "phones": [], "all_entities": [], "total_detected": 0}

    # Extract raw matches
    raw_names = re.findall(REGEX_PATTERNS_EXTRACTION["name"], text)
    cleaned_names = []
    for nm in raw_names:
        words = nm.split()
        if len(words) >= 3 and words[0] in COMMON_NON_NAME_WORDS:
            cleaned_names.append(" ".join(words[1:]))
        elif words[0] not in COMMON_NON_NAME_WORDS or len(words) >= 2:
            cleaned_names.append(nm)

    # Clean duplicates while preserving order
    name_matches = list(dict.fromkeys(cleaned_names))
    email_matches = list(dict.fromkeys(re.findall(REGEX_PATTERNS_EXTRACTION["email"], text)))
    phone_matches = list(dict.fromkeys(re.findall(REGEX_PATTERNS_EXTRACTION["phone"], text)))
    # Clean up phone matches (ensure at least 7 digits to avoid false positives like numbers)
    phone_matches = [p for p in phone_matches if len(re.sub(r'\D', '', p)) >= 7]

    all_entities = []
    for m in re.finditer(REGEX_PATTERNS_EXTRACTION["name"], text):
        val = m.group(0)
        words = val.split()
        if len(words) >= 3 and words[0] in COMMON_NON_NAME_WORDS:
            val = " ".join(words[1:])
        all_entities.append({"type": "name", "value": val, "start": m.start(), "end": m.end()})
    for m in re.finditer(REGEX_PATTERNS_EXTRACTION["email"], text):
        all_entities.append({"type": "email", "value": m.group(0), "start": m.start(), "end": m.end()})
    for m in re.finditer(REGEX_PATTERNS_EXTRACTION["phone"], text):
        val = m.group(0)
        if len(re.sub(r'\D', '', val)) >= 7:
            all_entities.append({"type": "phone", "value": val, "start": m.start(), "end": m.end()})

    # Sort all entities by starting position in document
    all_entities.sort(key=lambda x: x["start"])

    return {
        "names": name_matches,
        "emails": email_matches,
        "phones": phone_matches,
        "all_entities": all_entities,
        "total_detected": len(name_matches) + len(email_matches) + len(phone_matches)
    }


# ============================================================
# 2. PYDANTIC MODELS
# ============================================================

class SubmitFormRequest(BaseModel):
    name: str = Field(..., description="Full Name")
    email: str = Field(..., description="Email Address")
    phone: Optional[str] = Field(default=None, description="Phone Number")
    phone_number: Optional[str] = Field(default=None, description="Alternative Phone Number field")
    document_text: Optional[str] = Field(default="", description="Optional text/document to scan for regex patterns")
    notes: Optional[str] = Field(default="", description="Additional notes or message")
    create_onlyoffice_doc: bool = Field(default=True, description="Whether to create an OnlyOffice document")
    index_in_rag: bool = Field(default=False, description="Whether to index document in RAG vector store")

    def get_phone(self) -> str:
        return (self.phone or self.phone_number or "").strip()


class RegexDetectRequest(BaseModel):
    text: str = Field(..., description="Document text to scan for regex patterns")


class IngestTextRequest(BaseModel):
    title: str = Field(..., description="Document Title")
    source: str = Field(..., description="Source filename or identifier")
    text: str = Field(..., description="Plain text document content")


class AskRequest(BaseModel):
    question: str = Field(..., description="Question to answer using indexed documents")
    top_k: Optional[int] = Field(default=TOP_K, ge=1, le=20, description="Number of context chunks to retrieve")


# ============================================================
# 3. ONLYOFFICE HELPER FUNCTIONS
# ============================================================

def _document_type(filename: str) -> str:
    """Return OnlyOffice document type."""
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".txt": "word",
        ".doc": "word",
        ".docx": "word",
        ".odt": "word",
        ".rtf": "word",
        ".xls": "cell",
        ".xlsx": "cell",
        ".csv": "cell",
        ".ods": "cell",
        ".ppt": "slide",
        ".pptx": "slide",
        ".odp": "slide",
    }
    return mapping.get(ext, "word")


def build_onlyoffice_url(filename: str, original_name: str) -> str:
    """Build URL to open file via our editor.html which uses DocsAPI."""
    file_url = f"{INTERNAL_BASE_URL}/uploads/{quote(filename)}"
    key = hashlib.sha1(f"{filename}:{original_name}".encode("utf-8")).hexdigest()
    return (
        f"{APP_BASE_URL}/static/editor.html"
        f"?fileName={quote(original_name)}"
        f"&fileext={quote(Path(original_name).suffix)}"
        f"&url={quote(file_url)}"
        f"&documentType={_document_type(original_name)}"
        f"&key={key}"
    )


def create_docx_document(file_path: Path, name: str, email: str, phone: str, notes: str, doc_text: str, detected: dict):
    """Generate a styled Microsoft Word (.docx) document with regex report and detected entities."""
    try:
        import docx
        doc = docx.Document()
        
        # Title
        doc.add_heading("Form Submission & Regex Analysis Report", level=0)
        
        # Submitter details
        doc.add_heading("1. Submitter Information", level=1)
        table = doc.add_table(rows=4, cols=2)
        table.style = 'Table Grid'
        
        row_data = [
            ("Full Name", name),
            ("Email Address", email),
            ("Phone Number", phone),
            ("Notes / Remarks", notes or "None")
        ]
        for i, (k, v) in enumerate(row_data):
            table.cell(i, 0).paragraphs[0].add_run(k).bold = True
            table.cell(i, 1).text = v
            
        # Regex Patterns in Document
        doc.add_heading("2. Defined Regex Patterns in Document", level=1)
        p = doc.add_paragraph()
        p.add_run("• Name Regex Pattern: ").bold = True
        p.add_run(REGEX_PATTERNS_VALIDATION["name"])
        
        p2 = doc.add_paragraph()
        p2.add_run("• Email Regex Pattern: ").bold = True
        p2.add_run(REGEX_PATTERNS_VALIDATION["email"])
        
        p3 = doc.add_paragraph()
        p3.add_run("• Phone Regex Pattern: ").bold = True
        p3.add_run(REGEX_PATTERNS_VALIDATION["phone"])
        
        # Detected Entities
        doc.add_heading("3. Detected Entities in Document Content", level=1)
        doc.add_paragraph(f"Total Entities Detected: {detected.get('total_detected', 0)}")
        
        doc.add_paragraph(f"• Detected Names: {', '.join(detected.get('names', [])) if detected.get('names') else 'None'}")
        doc.add_paragraph(f"• Detected Emails: {', '.join(detected.get('emails', [])) if detected.get('emails') else 'None'}")
        doc.add_paragraph(f"• Detected Phone Numbers: {', '.join(detected.get('phones', [])) if detected.get('phones') else 'None'}")
        
        # Document Content
        doc.add_heading("4. Document Body Content", level=1)
        doc.add_paragraph(doc_text if doc_text else "[No additional document text provided]")
        
        doc.save(str(file_path))
        return True
    except Exception:
        return False


# ============================================================
# 4. FORM SUBMIT & REGEX ENDPOINTS
# ============================================================

@api.get("/api/regex/patterns")
@api.get("/regex-patterns")
def get_regex_patterns():
    """Return configured regular expression patterns for validation and entity extraction."""
    return {
        "validation_patterns": REGEX_PATTERNS_VALIDATION,
        "extraction_patterns": REGEX_PATTERNS_EXTRACTION,
        "descriptions": {
            "name": "Matches person full names (letters, spaces, dots, hyphens)",
            "email": "Matches standard RFC 5322 email addresses",
            "phone": "Matches international and local phone numbers with optional country code, dashes/spaces"
        }
    }


@api.get("/api/regex/test")
@api.get("/test-regex")
def test_regex_endpoint():
    """Run built-in regex pattern tests and return results."""
    test_cases = {
        "name": [
            {"value": "Hamza Ali", "expected": True},
            {"value": "Sarah Johnson", "expected": True},
            {"value": "12345", "expected": False},
            {"value": "A", "expected": False}
        ],
        "email": [
            {"value": "hamza@cyberify.ai", "expected": True},
            {"value": "test.user@domain.com", "expected": True},
            {"value": "invalid-email@", "expected": False},
            {"value": "user@domain..com", "expected": False}
        ],
        "phone": [
            {"value": "+92 300 1234567", "expected": True},
            {"value": "0300-1234567", "expected": True},
            {"value": "+1 (415) 555-0199", "expected": True},
            {"value": "123", "expected": False}
        ]
    }
    
    results = {}
    for entity, cases in test_cases.items():
        pattern = REGEX_PATTERNS_VALIDATION[entity]
        results[entity] = []
        for case in cases:
            matched = bool(re.match(pattern, case["value"]))
            passed = (matched == case["expected"])
            results[entity].append({
                "test_input": case["value"],
                "matched": matched,
                "passed": passed
            })
            
    return {"status": "success", "results": results}


@api.post("/api/regex/detect")
def detect_regex_endpoint(req: RegexDetectRequest):
    """Detect names, emails, and phone numbers in any document or plain text using regex."""
    if not req.text or not req.text.strip():
        return {
            "names": [],
            "emails": [],
            "phones": [],
            "all_entities": [],
            "total_detected": 0
        }
    return detect_regex_entities(req.text)


@api.post("/api/submit")
@api.post("/submit")
def submit_form_endpoint(req: SubmitFormRequest):
    """
    Submit form with Name, Email, Phone Number, validate with Regex,
    scan document text for regex patterns, and optionally generate an OnlyOffice document (.docx).
    """
    phone_value = req.get_phone()

    # 1. Validate Form Fields with Regex
    validation_results = {}
    errors = []

    # Validate Name
    is_name_valid = bool(re.match(REGEX_PATTERNS_VALIDATION["name"], req.name.strip()))
    validation_results["name"] = {"valid": is_name_valid, "value": req.name}
    if not is_name_valid:
        errors.append("Invalid Name format. Name should contain 2-60 alphabetic characters, spaces, dots or hyphens.")

    # Validate Email
    is_email_valid = bool(re.match(REGEX_PATTERNS_VALIDATION["email"], req.email.strip()))
    validation_results["email"] = {"valid": is_email_valid, "value": req.email}
    if not is_email_valid:
        errors.append("Invalid Email address format. Example: user@example.com")

    # Validate Phone
    is_phone_valid = bool(re.match(REGEX_PATTERNS_VALIDATION["phone"], phone_value))
    validation_results["phone"] = {"valid": is_phone_valid, "value": phone_value}
    if not is_phone_valid:
        errors.append("Invalid Phone Number format. Example: +92 300 1234567 or 0300-1234567")

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Form validation failed", "errors": errors, "validation": validation_results}
        )

    # 2. Combine document text with form details for Regex entity extraction
    full_text_to_scan = f"{req.name}\n{req.email}\n{phone_value}\n{req.notes}\n\n{req.document_text or ''}"
    detected_entities = detect_regex_entities(full_text_to_scan)

    # Also detect specifically within the attached document text if provided
    doc_detected = detect_regex_entities(req.document_text) if req.document_text else detected_entities

    # 3. Create document for OnlyOffice (.docx format) if requested
    redirect_url = None
    saved_name = None
    rag_info = None

    if req.create_onlyoffice_doc:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', req.name.strip())
        doc_filename = f"Submission-{safe_name}-{uuid4().hex[:6]}.docx"
        saved_name = doc_filename
        target_path = UPLOAD_DIR / doc_filename

        # Generate styled DOCX file for OnlyOffice
        created_docx = create_docx_document(
            file_path=target_path,
            name=req.name,
            email=req.email,
            phone=phone_value,
            notes=req.notes or "",
            doc_text=req.document_text or "",
            detected=doc_detected
        )

        if not created_docx:
            # Fallback to .txt
            doc_filename = f"Submission-{safe_name}-{uuid4().hex[:6]}.txt"
            saved_name = doc_filename
            target_path = UPLOAD_DIR / doc_filename
            doc_content = (
                f"========================================================================\n"
                f"                FORM SUBMISSION & REGEX DETECTION REPORT                \n"
                f"========================================================================\n\n"
                f"Submission Timestamp : {now_str}\n"
                f"Submitter Name       : {req.name}\n"
                f"Submitter Email      : {req.email}\n"
                f"Submitter Phone      : {phone_value}\n"
                f"Notes / Remarks      : {req.notes or 'None'}\n\n"
                f"------------------------------------------------------------------------\n"
                f"                      REGEX PATTERNS ANALYSIS SUMMARY                   \n"
                f"------------------------------------------------------------------------\n"
                f"• Name Regex Pattern  : {REGEX_PATTERNS_VALIDATION['name']}\n"
                f"  Status              : VALID [Passed]\n\n"
                f"• Email Regex Pattern : {REGEX_PATTERNS_VALIDATION['email']}\n"
                f"  Status              : VALID [Passed]\n\n"
                f"• Phone Regex Pattern : {REGEX_PATTERNS_VALIDATION['phone']}\n"
                f"  Status              : VALID [Passed]\n\n"
                f"------------------------------------------------------------------------\n"
                f"                   DETECTED ENTITIES IN DOCUMENT CONTENT                \n"
                f"------------------------------------------------------------------------\n"
                f"Total Entities Found : {doc_detected['total_detected']}\n"
                f"• Detected Names     : {', '.join(doc_detected['names']) if doc_detected['names'] else 'None'}\n"
                f"• Detected Emails    : {', '.join(doc_detected['emails']) if doc_detected['emails'] else 'None'}\n"
                f"• Detected Phones    : {', '.join(doc_detected['phones']) if doc_detected['phones'] else 'None'}\n\n"
                f"------------------------------------------------------------------------\n"
                f"                           ATTACHED DOCUMENT TEXT                       \n"
                f"------------------------------------------------------------------------\n"
                f"{req.document_text if req.document_text else '[No additional document text provided]'}\n\n"
                f"========================================================================\n"
                f"Generated via Cyberify RAG & OnlyOffice Platform\n"
            )
            target_path.write_text(doc_content, encoding="utf-8")

        redirect_url = build_onlyoffice_url(saved_name, saved_name)

        # Optional RAG Ingestion
        if req.index_in_rag:
            try:
                rag_info = ingest.ingest_document(
                    title=f"Form Submission - {req.name}",
                    source=doc_filename,
                    text=f"{req.name}\n{req.email}\n{phone_value}\n{req.document_text or ''}"
                )
            except Exception as e:
                rag_info = {"error": f"Failed to ingest into RAG: {str(e)}"}

    return {
        "status": "success",
        "message": "Form submitted successfully and regex patterns validated!",
        "validation": validation_results,
        "detected_entities": doc_detected,
        "document_filename": saved_name,
        "redirect_url": redirect_url,
        "rag_ingested": rag_info is not None and "error" not in rag_info,
        "rag_info": rag_info
    }


# ============================================================
# 5. RAG & ONLYOFFICE ENDPOINTS
# ============================================================

@api.get("/api/health")
def health():
    try:
        rows = db.query("SELECT COUNT(*)::int AS chunks FROM chunks")
        chunk_count = rows[0]["chunks"] if rows else 0
    except Exception:
        chunk_count = 0

    return {
        "status": "ok",
        "chunks_indexed": chunk_count,
        "embedding_model": EMBEDDING_MODEL,
        "chat_model": CHAT_MODEL,
    }


@api.get("/api/documents")
def get_documents():
    """List all indexed documents with chunk count."""
    try:
        return ingest.list_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api.post("/api/ingest")
def ingest_text(req: IngestTextRequest):
    """Ingest a text document into the RAG vector database."""
    try:
        res = ingest.ingest_document(title=req.title, source=req.source, text=req.text)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@api.post("/api/ingest/file")
async def ingest_file_endpoint(file: UploadFile = File(...)):
    """Upload and ingest a text/markdown file into the RAG vector database."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        content_bytes = await file.read()
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = content_bytes.decode("latin-1", errors="ignore")

        if not text.strip():
            raise HTTPException(status_code=400, detail="File is empty or contains no readable text")

        res = ingest.ingest_document(
            title=file.filename,
            source=file.filename,
            text=text
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest file: {str(e)}")


@api.delete("/api/documents/{document_id}")
def delete_document_endpoint(document_id: int):
    """Delete a document and its chunks from the database."""
    try:
        deleted = ingest.delete_document(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"status": "deleted", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api.post("/api/ask")
def ask_question_endpoint(req: AskRequest):
    """Ask a question; returns an answer grounded exclusively in indexed documents."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        top_k = req.top_k or TOP_K
        result = rag.answer_question(req.question, top_k=top_k)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@api.post("/api/upload")
async def upload_file(file: UploadFile = File(...), also_ingest: bool = False):
    """Upload file for OnlyOffice editor and optionally index into RAG vector DB."""
    if file.filename is None or not file.filename.strip():
        raise HTTPException(status_code=400, detail="No file selected")

    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="File is empty")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Save to uploads directory
    original_name = Path(file.filename).name
    stem = Path(original_name).stem
    suffix = Path(original_name).suffix
    saved_name = f"{stem}-{uuid4().hex[:8]}{suffix}"
    target_path = UPLOAD_DIR / saved_name

    target_path.write_bytes(data)

    # Optional RAG Ingestion if plain text / md
    ingest_info = None
    if also_ingest and suffix.lower() in [".txt", ".md"]:
        try:
            text = data.decode("utf-8", errors="ignore")
            if text.strip():
                ingest_info = ingest.ingest_document(
                    title=original_name,
                    source=original_name,
                    text=text
                )
        except Exception:
            pass

    return {
        "status": "uploaded",
        "filename": file.filename,
        "redirect_url": build_onlyoffice_url(saved_name, file.filename),
        "rag_ingested": ingest_info is not None,
        "rag_info": ingest_info
    }


# ============================================================
# 6. STATIC FILES & ROOT ROUTE
# ============================================================

api.mount("/static", StaticFiles(directory="static"), name="static")
api.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@api.get("/")
def home():
    return FileResponse("static/index.html")


@api.get("/form")
def form_page():
    """Direct standalone HTML form page."""
    return FileResponse("static/form.html")

