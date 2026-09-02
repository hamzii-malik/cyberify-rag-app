"""Turn one long document into small, self-contained pieces.

Rule of thumb: a chunk should be big enough to answer a question on its own,
and small enough that it is about ONE thing.
"""

from app.config import CHUNK_CHARS, CHUNK_OVERLAP


def split_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    # 1. Break on blank lines first, so we never cut a paragraph in half.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # A single paragraph bigger than the limit gets cut on its own.
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(para), max_chars - overlap):
                chunks.append(para[i:i + max_chars])
            continue

        # Does it still fit in the chunk we are building?
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            chunks.append(current)
            # Carry the tail of the last chunk forward, so a fact that sits on
            # the boundary appears in BOTH chunks and cannot be lost.
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{para}" if tail else para

    if current:
        chunks.append(current)

    return chunks
