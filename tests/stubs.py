"""Offline stand-ins for the two OpenAI calls.

The fake embedding is a random projection: every word gets a fixed
pseudo-random direction (seeded from the word itself), and a text's vector
is the (normalised) sum of its words' directions. It has no idea that
"refund" and "money back" mean the same thing -- only the real model does --
but shared words do produce similar vectors, which is enough to exercise
every real piece of plumbing: Postgres, the vector column, cosine search,
and prompt assembly.
"""

import hashlib
import math
import re

from app.config import EMBEDDING_DIM

_WORD_RE = re.compile(r"[a-z0-9]+")


def _word_vector(word: str) -> list[float]:
    """A fixed, deterministic pseudo-random unit vector for one word."""
    vec = []
    seed = word.encode("utf-8")
    i = 0
    while len(vec) < EMBEDDING_DIM:
        h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        for j in range(0, len(h) - 1, 2):
            if len(vec) >= EMBEDDING_DIM:
                break
            raw = int.from_bytes(h[j:j + 2], "big")
            vec.append((raw / 65535.0) * 2 - 1)  # map to [-1, 1]
        i += 1
    return vec


def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    out = []
    for text in texts:
        words = _WORD_RE.findall(text.lower())
        if not words:
            words = ["empty"]
        summed = [0.0] * EMBEDDING_DIM
        for w in words:
            wv = _word_vector(w)
            for k in range(EMBEDDING_DIM):
                summed[k] += wv[k]
        norm = math.sqrt(sum(x * x for x in summed)) or 1.0
        out.append([x / norm for x in summed])
    return out


def fake_chat(system_prompt: str, user_prompt: str) -> str:
    """Return something recognisably stub-like, using the real context that was built."""
    if "CONTEXT:" in user_prompt:
        first_source_line = ""
        for line in user_prompt.splitlines():
            if line.startswith("[1]"):
                first_source_line = line
                break
        return f"[offline stub] Based on {first_source_line or 'the retrieved context'}, here is a placeholder answer."
    return "[offline stub] No context was provided."
