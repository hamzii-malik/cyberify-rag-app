"""Prove the RAG plumbing works with zero OpenAI calls.

Requires a running Postgres with the schema loaded (real DB, fake embeddings).

Usage:
    python -m tests.test_offline
"""

import sys

import app.embeddings as embeddings
import app.llm as llm
from tests.stubs import fake_embed_texts, fake_chat

# Monkeypatch the two OpenAI-backed functions with offline stand-ins,
# BEFORE importing anything that already bound the real ones.
embeddings.embed_texts = fake_embed_texts
embeddings.embed_one = lambda text: fake_embed_texts([text])[0]
llm.chat = fake_chat

from app import db, ingest, rag  # noqa: E402  (must come after the monkeypatch)

REFUND_TEXT = """Cyberify Refund Policy

Undamaged items may be returned within 14 days of delivery for a full refund.

Damaged items may be returned within 30 days of delivery. Please include photos of the damage.
"""

FAQ_TEXT = """Cyberify Internship FAQ

The internship runs for eight weeks, in small groups of three to four people.

Interns receive a certificate of completion if they finish at least 80 percent of the projects.
"""

passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if condition:
        passed += 1
    else:
        failed += 1


def main() -> None:
    # Clean slate for the two docs this test uses.
    for row in ingest.list_documents():
        if row["source"] in ("refund-policy.md", "internship-faq.md"):
            ingest.delete_document(row["id"])

    doc1 = ingest.ingest_document("Refund Policy", "refund-policy.md", REFUND_TEXT)
    doc2 = ingest.ingest_document("Internship FAQ", "internship-faq.md", FAQ_TEXT)
    check("two documents stored", doc1["document_id"] != doc2["document_id"])

    chunk_rows = db.query(
        "SELECT embedding FROM chunks WHERE document_id IN (%s, %s)",
        (doc1["document_id"], doc2["document_id"]),
    )
    check("chunks were created", len(chunk_rows) >= 2)
    def _dims(raw) -> int:
        s = str(raw).strip("[]")
        return len(s.split(",")) if s else 0

    check("every vector has 1536 dimensions", all(_dims(r["embedding"]) == 1536 for r in chunk_rows))

    hits = rag.answer_question("How long do I have to return a damaged item?")
    check("retrieval returned something", hits["used_context"] is True and len(hits["sources"]) > 0)
    check("top hit is the refund policy", hits["sources"][0]["source"] == "refund-policy.md")
    check("scores are between 0 and 1", all(0.0 <= s["score"] <= 1.0 for s in hits["sources"]))
    check(
        "scores come back sorted",
        all(hits["sources"][i]["score"] >= hits["sources"][i + 1]["score"] for i in range(len(hits["sources"]) - 1)),
    )

    other = rag.answer_question("How many people are in an internship group?")
    check(
        "a different question finds a different document",
        other["sources"] and other["sources"][0]["source"] == "internship-faq.md",
    )
    check("answer_question used context", hits["used_context"] is True)
    check("sources are numbered from 1", hits["sources"][0]["n"] == 1)

    nonsense = rag.answer_question("What is the airspeed velocity of an unladen swallow?")
    check("nonsense is filtered by min_score", nonsense["used_context"] is False)

    before = len(ingest.list_documents())
    ingest.delete_document(doc1["document_id"])
    after_chunks = db.query("SELECT COUNT(*)::int AS c FROM chunks WHERE document_id = %s", (doc1["document_id"],))
    check("deleting a document deleted its chunks", after_chunks[0]["c"] == 0)

    # cleanup
    ingest.delete_document(doc2["document_id"])

    print()
    print(f"=========  {passed} passed, {failed} failed  =========")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
