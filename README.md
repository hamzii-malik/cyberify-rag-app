# Cyberify RAG Chatbot

A chatbot that only knows your documents. FastAPI + PostgreSQL/pgvector + OpenAI
(`text-embedding-3-small` for embeddings, `gpt-4o-mini` for chat).

## ⚠️ About your API key

**Do not paste a real API key into chat, code, or commits.** Keys belong only in
`.env` (already `.gitignore`d). If you've ever pasted a key into a chat window,
a doc, or a public repo, treat it as compromised: revoke it at
https://platform.openai.com/api-keys and generate a new one.

## 1. Start Postgres with pgvector

```bash
docker run -d --name cyberify-pg \
    -e POSTGRES_USER=cyberify \
    -e POSTGRES_PASSWORD=cyberify123 \
    -e POSTGRES_DB=cyberify_rag \
    -p 5432:5432 \
    pgvector/pgvector:pg16
```

(No Docker? See the "Option B" note in the training deck — install `postgresql-16-pgvector`
on Ubuntu/Debian, or use a hosted Postgres that already ships pgvector. Avoid compiling it
on Windows.)

## 2. Create the database + extension, and load the schema

```bash
psql -h localhost -U postgres -c "CREATE DATABASE cyberify_rag OWNER cyberify;"
psql -h localhost -U cyberify -d cyberify_rag -f db/schema.sql
```

## 3. Python environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Configure secrets

```bash
cp .env.example .env
```

Open `.env` and paste in your **own, freshly rotated** `OPENAI_API_KEY`. Everything
else can stay at its default. `CHAT_MODEL` is already set to `gpt-4o-mini`.

## 5. Run it

```bash
uvicorn app.main:api --reload
```

In a second terminal, load the sample documents:

```bash
python -m scripts.ingest_folder seed
curl localhost:8000/api/health
```

Then open http://localhost:8000 (chat page) and http://localhost:8000/docs (interactive API).

For the dynamic CV workflow, open http://localhost:8000/cv-form. Upload a `.docx`,
`.txt`, or `.md` CV, review the detected fields, and submit to open an editable
DOCX in OnlyOffice. Set `APP_BASE_URL` and `INTERNAL_BASE_URL` to URLs reachable
by the OnlyOffice container when running the document server outside localhost.

## Testing without spending anything

The database half of RAG can be tested completely offline — only the two OpenAI
calls (embed + chat) are swapped for deterministic stand-ins in `tests/stubs.py`.

```bash
python -m tests.test_offline     # 12 checks against a real Postgres, fake OpenAI calls
python -m tests.serve_offline    # runs the full app with stub answers, no key at all
```

## Project layout

```
rag-app/
  app/
    config.py        every setting, read once from .env
    db.py             the connection pool
    chunking.py       long document  ->  small pieces
    embeddings.py     text  ->  1536 numbers  (OpenAI)
    llm.py            prompt -> answer      (OpenAI, gpt-4o-mini)
    ingest.py         Journey 1  end to end
    retrieval.py      Journey 2  step 3
    rag.py            Journey 2  steps 4 and 5
    main.py           the FastAPI endpoints
  db/
    schema.sql        two tables + the vector index
  static/
    index.html        the chat page
  seed/                sample documents
  tests/               offline test + offline demo server, no API key needed
  scripts/
    ingest_folder.py  bulk-load a folder of .md/.txt files
  .env                 your secrets  (never committed)
  .gitignore
  requirements.txt
```

## API endpoints

| Method | Path                    | Body                        | Returns                            |
|--------|-------------------------|------------------------------|-------------------------------------|
| GET    | `/api/health`           | —                             | `chunks_indexed`, model names        |
| POST   | `/api/ingest`           | `{title, source, text}`      | `document_id`, chunks created        |
| POST   | `/api/ingest/file`      | multipart file upload        | `document_id`, chunks created        |
| GET    | `/api/documents`        | —                             | every document + chunk count         |
| DELETE | `/api/documents/{id}`   | —                             | deleted id, or 404                   |
| POST   | `/api/ask`              | `{question, top_k}`          | `answer`, `sources[]`, `used_context`|

```bash
curl -X POST http://localhost:8000/api/ask \
    -H "Content-Type: application/json" \
    -d '{"question":"Can I return a damaged item after 20 days?"}'
```

## Common errors

| Error | Meaning |
|---|---|
| `type "vector" does not exist` | `CREATE EXTENSION` ran on a different database — check the psql prompt |
| `expression is of type text` | the `::vector` cast is missing from an INSERT or search query |
| `expected 1536 dimensions, not 3072` | you changed the embedding model but not the column — recreate the table and re-ingest |
| `AuthenticationError: 401` | `OPENAI_API_KEY` is missing/misspelled, or `.env` isn't next to the file you ran |
| `RateLimitError: 429` | too many calls too fast, or no credit on the account — batch your embeddings |
| `ModuleNotFoundError: app` | run `uvicorn app.main:api` from the project root, not `python app/main.py` |
| Everything answers "could not find" | nothing is ingested, or `MIN_SCORE` is too high — check `/api/health` first |
| Answers ignore the documents | rule 1 was dropped from the system prompt, or `top_k` returned nothing and you still called the model |
| Search feels slow | the HNSW index is missing, or you searched with `<->` while the index is cosine |
