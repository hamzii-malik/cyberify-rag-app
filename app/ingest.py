"""Journey 1 — INDEXING. Document in, chunks + vectors in the database."""

from app import db
from app.chunking import split_text
from app.embeddings import embed_texts, to_pgvector


def ingest_document(title: str, source: str, text: str) -> dict:
    chunks = split_text(text)
    if not chunks:
        raise ValueError("Nothing to ingest — the text is empty.")

    # 1. One row in documents (the parent).
    doc = db.execute(
        "INSERT INTO documents (title, source) VALUES (%s, %s) RETURNING id, title, source",
        (title, source),
    )

    # 2. Embed EVERY chunk in one API call.
    vectors = embed_texts(chunks)

    # 3. One row per chunk (the children), each carrying its vector.
    for i, (content, vector) in enumerate(zip(chunks, vectors)):
        db.execute(
            """INSERT INTO chunks (document_id, chunk_index, content, n_chars, embedding)
               VALUES (%s, %s, %s, %s, %s::vector)
               ON CONFLICT (document_id, chunk_index) DO UPDATE
                 SET content = EXCLUDED.content,
                     n_chars = EXCLUDED.n_chars,
                     embedding = EXCLUDED.embedding""",
            (doc["id"], i, content, len(content), to_pgvector(vector)),
        )

    return {"document_id": doc["id"], "title": title, "source": source, "chunks": len(chunks)}


def list_documents() -> list[dict]:
    return db.query(
        """SELECT d.id, d.title, d.source, d.created_at,
                  COUNT(c.id)::int AS chunk_count
           FROM documents d
           LEFT JOIN chunks c ON c.document_id = d.id
           GROUP BY d.id
           ORDER BY d.id"""
    )


def delete_document(document_id: int) -> int:
    # ON DELETE CASCADE removes every chunk of this document for us.
    row = db.execute("DELETE FROM documents WHERE id = %s RETURNING id", (document_id,))
    return 1 if row else 0
