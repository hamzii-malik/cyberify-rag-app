"""FastAPI app: Cyberify RAG Chatbot + OnlyOffice Document Integration."""

import hashlib
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, ingest, patterns, rag, signature
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


class IngestTextRequest(BaseModel):
    title: str = Field(..., description="Document Title")
    source: str = Field(..., description="Source filename or identifier")
    text: str = Field(..., description="Plain text document content")


class AskRequest(BaseModel):
    question: str = Field(..., description="Question to answer using indexed documents")
    top_k: Optional[int] = Field(default=TOP_K, ge=1, le=20, description="Number of context chunks to retrieve")


class ContactFormRequest(BaseModel):
    name: str = Field(..., description="Full name, e.g. Ali Raza")
    email: str = Field(..., description="Email address")
    phone: str = Field(..., description="Pakistani mobile number, e.g. 0300-1234567")
    gender: str = Field(..., description="Gender: male or female")
    signature_b64: Optional[str] = Field(default=None, description="Base64-encoded PNG of the candidate e-signature")


class DetectTextRequest(BaseModel):
    text: Optional[str] = Field(default=None, description="Raw text to scan")
    document_id: Optional[int] = Field(default=None, description="Scan an already-ingested document instead")


class CVSubmitRequest(BaseModel):
    title: str = Field(default="My CV", max_length=120)
    fields: list[dict] = Field(..., min_length=1, max_length=50)


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


# ---------- Contact Form + Regex Pattern Detection ----------
@api.post("/api/submit-form")
def submit_form(req: ContactFormRequest):
    """Validate the Name / Email / Phone / Gender fields with regex, then save
    the submission along with an optional base64-encoded e-signature PNG.
    Returns per-field validation results; if any field fails its pattern the
    whole submission is rejected with a 400."""
    name = req.name.strip()
    email = req.email.strip()
    phone = req.phone.strip()
    gender = req.gender.strip().lower()

    # --- Field Regex Validation ---
    checks = {
        "name": patterns.validate_field("name", name),
        "email": patterns.validate_field("email", email),
        "phone": patterns.validate_field("phone", phone),
        "gender": patterns.validate_field("gender", gender),
        "signature": bool(req.signature_b64)
        and patterns.validate_field("signature", req.signature_b64),
    }

    if not all(checks.values()):
        raise HTTPException(
            status_code=400,
            detail={"message": "One or more fields failed pattern validation.", "valid": checks},
        )

    # --- Validate and save the e-signature PNG ---
    sig_path: Path | None = None
    sig_db_path: str | None = None
    if req.signature_b64:
        try:
            sig_path, sig_db_path = signature.save_signature(req.signature_b64, UPLOAD_DIR)
        except signature.SignatureError as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature image: {e}")

    try:
        row = db.execute(
            "INSERT INTO submissions (name, email, phone, gender, signature_path) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at",
            (name, email, phone, gender, sig_db_path),
        )
        row_id = row["id"] if row else uuid4().hex[:6]

        # Generate DOCX document for OnlyOffice
        original_name = f"Contact_Record_{row_id}_{name.replace(' ', '_')}.docx"
        saved_name = f"contact-{row_id}-{uuid4().hex[:8]}.docx"
        doc_path = UPLOAD_DIR / saved_name
        patterns.create_contact_document(
            doc_path, name, email, phone,
            gender=gender,
            signature_path=sig_path,
        )

        onlyoffice_url = build_onlyoffice_url(saved_name, original_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save submission: {str(e)}")

    return {
        "status": "submitted",
        "id": row["id"] if row else None,
        "created_at": str(row["created_at"]) if row else None,
        "valid": checks,
        "data": {"name": name, "email": email, "phone": phone, "gender": gender},
        "patterns_defined": {
            "name_pattern": "{name}",
            "email_pattern": "[email]",
            "contact_pattern": "(contact)",
            "name_regex": r"^[A-Za-z]+(?:[ \t.'-][A-Za-z]+)*$",
            "email_regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "contact_regex": r"(?:\+92[\s-]?)?0?3\d{2}[\s-]?\d{7}",
            "gender_regex": r"^(?:male|female)$",
            "signature_regex": r"^data:image/png;base64,[A-Za-z0-9+/]+={0,2}$",
        },
        "onlyoffice_url": onlyoffice_url
    }


@api.post("/api/detect-patterns")
def detect_patterns_endpoint(req: DetectTextRequest):
    """Run the name/email/phone regex patterns over either raw `text` or an
    already-ingested `document_id` and return everything they find."""
    if req.document_id is not None:
        rows = db.query(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (req.document_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Document not found or has no chunks")
        text = "\n".join(r["content"] for r in rows)
    elif req.text is not None and req.text.strip():
        text = req.text
    else:
        raise HTTPException(status_code=400, detail="Provide either 'text' or 'document_id'")

    return patterns.detect_patterns(text)


# ---------- Dynamic CV Form ----------
@api.post("/api/cv/analyze")
async def analyze_cv(file: UploadFile = File(...)):
    """Extract editable fields from an uploaded CV template."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".docx", ".txt", ".md"):
        raise HTTPException(status_code=400, detail="Upload a .docx, .txt, or .md CV")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    temp_path = UPLOAD_DIR / f"_cv-{uuid4().hex}{suffix}"
    temp_path.write_bytes(data)
    try:
        text = patterns.extract_text_from_file(temp_path)
        fields = patterns.extract_cv_fields(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CV: {e}") from e
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "filename": Path(file.filename).name,
        "fields": fields,
        "validators": patterns.validator_sources(),
    }


@api.post("/api/cv/submit")
def submit_cv(req: CVSubmitRequest):
    """Create the edited CV as DOCX and open it in OnlyOffice."""
    clean_fields = []
    for index, field in enumerate(req.fields):
        label = str(field.get("label", "")).strip()[:80]
        value = str(field.get("value", "")).strip()[:10000]
        key = str(field.get("key", f"field_{index}")).strip()[:80]
        field_type = str(field.get("type", "text")).strip()[:20]
        if label and value:
            validator = field.get("validator") or patterns.infer_cv_validator(label, key, field_type)
            clean_fields.append({
                "label": label,
                "value": value,
                "key": key,
                "type": field_type,
                "validator": validator,
                "regex": patterns.cv_field_regex(validator),
            })
    if not clean_fields:
        raise HTTPException(status_code=400, detail="Enter at least one CV field")

    invalid = patterns.validate_cv_fields(clean_fields)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "One or more CV fields failed pattern validation.",
                "invalid": invalid,
            },
        )

    saved_name = f"cv-{uuid4().hex[:12]}.docx"
    original_name = re.sub(r"[^A-Za-z0-9 _.-]", "", req.title).strip() or "My CV"
    if not original_name.lower().endswith(".docx"):
        original_name += ".docx"
    try:
        patterns.create_cv_document(UPLOAD_DIR / saved_name, clean_fields, Path(original_name).stem)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create CV: {e}") from e
    return {
        "status": "saved",
        "fields": clean_fields,
        "onlyoffice_url": build_onlyoffice_url(saved_name, original_name),
    }


@api.post("/api/detect-patterns/file")
async def detect_patterns_file_endpoint(file: UploadFile = File(...)):
    """Upload a document file (.txt/.md/.docx — e.g. one edited in OnlyOffice)
    directly and run the regex patterns over its extracted text."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".txt", ".md", ".docx"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    data = await file.read()
    tmp_path = UPLOAD_DIR / f"_scan-{uuid4().hex[:8]}{suffix}"
    tmp_path.write_bytes(data)
    try:
        text = patterns.extract_text_from_file(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"filename": file.filename, **patterns.detect_patterns(text)}


# ---------- OnlyOffice Endpoints ----------
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
        f"&callbackUrl={quote(f'{APP_BASE_URL}/api/onlyoffice/callback/{quote(filename)}')}"
        f"&key={key}"
    )


@api.post("/api/onlyoffice/callback/{filename}")
async def onlyoffice_callback(filename: str, payload: dict):
    """Persist the DOCX that OnlyOffice sends after a user saves it."""
    status = payload.get("status")
    download_url = payload.get("url")
    if status in (2, 6) and download_url:
        try:
            with urlopen(download_url, timeout=30) as response:
                data = response.read()
            target = UPLOAD_DIR / Path(filename).name
            target.write_bytes(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save OnlyOffice document: {e}") from e
    return {"error": 0}


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


# Serve static files, uploads, and homepage
api.mount("/static", StaticFiles(directory="static"), name="static")
api.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@api.get("/")
def home():
    return FileResponse("static/index.html")


@api.get("/form")
def contact_form_page():
    return FileResponse("static/form.html")


@api.get("/cv-form")
def cv_form_page():
    return FileResponse("static/cv-form.html")
