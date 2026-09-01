"""Journey 2, steps 4 and 5 — build the prompt, then answer from it."""

from app.llm import chat
from app.retrieval import search
from app.config import TOP_K

SYSTEM_PROMPT = """You are the Cyberify assistant.

Rules you must follow:
1. Answer ONLY from the CONTEXT below. Never use outside knowledge.
2. If the context does not contain the answer, reply exactly:
   "I could not find this in the documents."
3. Cite the source number in square brackets after every fact, like [1].
4. Be brief. Two or three sentences is usually enough.
"""


def build_context(hits: list[dict]) -> str:
    """Number every chunk so the model has something to cite."""
    blocks = []
    for i, hit in enumerate(hits, start=1):
        blocks.append(f"[{i}] ({hit['source']}, chunk {hit['chunk_index']})\n{hit['content']}")
    return "\n\n".join(blocks)


def answer_question(question: str, top_k: int = TOP_K) -> dict:
    hits = search(question, top_k=top_k)

    # Nothing relevant? Do not call the model at all — it would only guess.
    if not hits:
        return {
            "answer": "I could not find this in the documents.",
            "sources": [],
            "used_context": False,
        }

    context = build_context(hits)
    user_prompt = f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"

    return {
        "answer": chat(SYSTEM_PROMPT, user_prompt),
        "sources": [
            {
                "n": i,
                "title": h["title"],
                "source": h["source"],
                "chunk_index": h["chunk_index"],
                "score": round(float(h["score"]), 4),
            }
            for i, h in enumerate(hits, start=1)
        ],
        "used_context": True,
    }
