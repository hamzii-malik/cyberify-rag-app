-- ============================================================
--  Cyberify RAG — database schema
--  Run this ONCE:  psql -U cyberify -d cyberify_rag -f db/schema.sql
-- ============================================================

-- pgvector adds a new column type called "vector".
-- Without this line, VECTOR(1536) below is a syntax error.
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per file you feed the system.
CREATE TABLE IF NOT EXISTS documents (
  id          SERIAL       PRIMARY KEY,
  title       VARCHAR(300) NOT NULL,
  source      VARCHAR(300) NOT NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- One row per piece of that file. THIS is what we search.
CREATE TABLE IF NOT EXISTS chunks (
  id           SERIAL       PRIMARY KEY,
  document_id  INTEGER      NOT NULL
               REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index  INTEGER      NOT NULL,
  content      TEXT         NOT NULL,
  n_chars      INTEGER      NOT NULL,
  embedding    VECTOR(1536) NOT NULL,
  created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
  UNIQUE (document_id, chunk_index)
);

-- Without this index Postgres compares your question to EVERY row.
-- With it, it only looks at the near neighbours. Same answers, far less work.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
  ON chunks USING hnsw (embedding vector_cosine_ops);

-- Contact form submissions (Name / Email / Phone), validated with regex
-- patterns (app/patterns.py) before being written here.
CREATE TABLE IF NOT EXISTS submissions (
  id          SERIAL       PRIMARY KEY,
  name        VARCHAR(150) NOT NULL,
  email       VARCHAR(200) NOT NULL,
  phone       VARCHAR(50)  NOT NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);
