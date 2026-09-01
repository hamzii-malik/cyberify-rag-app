"""Run the whole app with stub embeddings + stub chat. No OpenAI key needed.

Usage:
    python -m tests.serve_offline
Then open http://localhost:8000
"""

import uvicorn

import app.embeddings as embeddings
import app.llm as llm
from tests.stubs import fake_embed_texts, fake_chat

embeddings.embed_texts = fake_embed_texts
embeddings.embed_one = lambda text: fake_embed_texts([text])[0]
llm.chat = fake_chat

from app.main import api  # noqa: E402  (must come after the monkeypatch)

if __name__ == "__main__":
    uvicorn.run(api, host="127.0.0.1", port=8000)
