# Database and vector-store migration (ChromaDB -> Supabase pgvector)

> **Status: prepared, NOT executed.** No production database, Chroma directory or
> bucket has been touched. Everything below is for you to run, in order, on your
> own schedule. Every step has a rollback and none deletes source data.

## 1. Current storage architecture

| Data | Store | Notes |
|---|---|---|
| Users, profiles, conversations, workouts, memories, activity, documents (metadata) | PostgreSQL (Supabase) | Alembic 0001-0004. Unchanged. |
| Vectors | ChromaDB, local directory (`CHROMADB_PERSIST_DIR`, default `backend/chroma_data`) | Collections below. |
| Embeddings | Chroma default ONNX **all-MiniLM-L6-v2, 384 dimensions, cosine** | `EMBEDDING_NAME = chroma-default-onnx-minilm-l6-v2` is stored in each collection's metadata. |
| Uploaded originals | local `UPLOAD_DIR` | Lost on Render Free restarts. |

ChromaDB collections (all `hnsw:space = cosine`):

| Collection | Owner-scoped | Metadata keys (scalars only) |
|---|---|---|
| `fitness_knowledge` | no (shared, curated) | `doc_id, source, file_type, page, chunk_index, scope` (+ custom) |
| `user_documents` | yes (`owner_id`) | as above + `owner_id, storage_key, content_type` |
| `user_continuity` | yes (`owner_id`) | `kind` (`memory`/`summary`), `key` or `conversation_id`, `source`, `title` |

Chunk ids: `{sha256(owner)[:12]}:{doc_id}:{chunk_index}` for user documents; `memory:<key>` /
`summary:<conversation_id>` for continuity.

## 2. Target schema

Migration `0005_ingestion_jobs_pgvector` (purely additive, idempotent `IF NOT EXISTS`):

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vector_chunks (
    collection      text        NOT NULL,          -- fitness_knowledge | user_documents | user_continuity
    id              text        NOT NULL,          -- same ids as Chroma
    owner_id        text,                          -- NULL for the shared collection
    doc_id          text,
    content         text        NOT NULL,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(384) NOT NULL,
    embedding_model text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection, id)
);
CREATE INDEX IF NOT EXISTS ix_vector_chunks_scope ON vector_chunks (collection, owner_id, doc_id);
CREATE INDEX IF NOT EXISTS ix_vector_chunks_embedding_hnsw
    ON vector_chunks USING hnsw (embedding vector_cosine_ops);

-- plus document_ingestion_jobs (one row per document; checkpoint + lease columns)
```

* **Distance**: `embedding <=> query` is pgvector's cosine distance, i.e. the same
  `1 - cos` Chroma returns, so `Retriever` scores (`1 - distance`) are unchanged.
* **Dimension**: `vector(384)` is fixed in the table. Writes with any other length are rejected
  in Python (`EMBEDDING_DIMENSION`) *and* by PostgreSQL. Changing the model/dimension requires a
  new migration and a full re-embed; there is no in-place conversion.
* **Index**: HNSW with cosine ops (no training step, good recall at small/medium scale). The
  btree on `(collection, owner_id, doc_id)` serves owner-scoped filters and per-document deletes.
* **Extensions**: `vector` (pgvector). Supabase: Dashboard -> Database -> Extensions -> `vector`
  (the migration enables it if your role may).

## 3. Rollback of the schema migration

`alembic downgrade -1` drops `vector_chunks` and `document_ingestion_jobs` only (both are new
and derived). The `vector` extension is left installed. No pre-existing table is touched.
Verified against a real Postgres 16 + pgvector container (`tests/unit/deploy/test_pgvector_integration.py`):
upgrade -> downgrade -> upgrade, with `documents` intact.

## 4. Procedure

### 4.0 Backups (do not skip)

```bash
# PostgreSQL (use the direct, non-pooled connection string)
pg_dump "$DIRECT_DATABASE_URL" -Fc -f fitai-$(date +%F).dump
# Chroma: stop writers, then copy the whole directory
cp -a backend/chroma_data backend/chroma_data.bak-$(date +%F)
# Uploaded originals, if any are still on local disk
cp -a backend/uploads backend/uploads.bak-$(date +%F)
```

Supabase also offers point-in-time recovery / daily backups on paid plans; check yours.

### 4.1 Apply the schema (one-off, manual)

From any machine with network access to the database (the image already contains Alembic):

```bash
docker run --rm -e DATABASE_URL="$DIRECT_DATABASE_URL" -e ENVIRONMENT=development \
  --entrypoint alembic fitai-core:latest upgrade head
```

or `cd backend && DATABASE_URL=... alembic upgrade head`. The containers themselves **never**
migrate; they only verify the head at start-up and refuse to boot if it is behind.

### 4.2 Check the embedding provider (R1 in the audit)

```bash
cd backend
EMBEDDING_API_URL=... EMBEDDING_API_KEY=... python scripts/verify_embedding_parity.py
```

Proceed to 4.3 only on `PARITY OK`. If it fails, skip 4.3 and re-ingest your documents through
the Documents service instead (new embeddings, no copy).

### 4.3 Copy existing vectors (dry run first)

```bash
cd backend
export DATABASE_URL="$DIRECT_DATABASE_URL"
python scripts/migrate_chroma_to_pgvector.py --chroma-dir ./chroma_data            # dry run
python scripts/migrate_chroma_to_pgvector.py --chroma-dir ./chroma_data --apply    # copy
python scripts/migrate_chroma_to_pgvector.py --chroma-dir ./chroma_data --verify   # compare
```

Properties: reads Chroma only (never writes or deletes), copies stored embeddings verbatim (no
re-embedding), rejects any vector whose length is not 384, upserts idempotently (re-run after any
interruption), prints per-collection counts.

### 4.4 Validation queries

```sql
-- counts per collection must equal the Chroma counts printed by --verify
SELECT collection, count(*) FROM vector_chunks GROUP BY 1 ORDER BY 1;

-- dimension must be 384 everywhere; model tag must be the expected one
SELECT collection, count(*) AS n, min(vector_dims(embedding)) AS dim_min,
       max(vector_dims(embedding)) AS dim_max, max(embedding_model) AS model
FROM vector_chunks GROUP BY 1;

-- owner isolation: no owner-scoped row without an owner
SELECT count(*) FROM vector_chunks
WHERE collection IN ('user_documents','user_continuity') AND owner_id IS NULL;      -- expect 0

-- documents that claim to be indexed but have no vectors (chunks == 0 is legitimate
-- only for an empty file)
SELECT d.id, d.filename FROM documents d
LEFT JOIN vector_chunks v ON v.doc_id = d.id::text AND v.collection = 'user_documents'
WHERE d.status = 'indexed' GROUP BY d.id, d.filename HAVING count(v.id) = 0;

-- spot-check retrieval quality with a stored vector as the query
SELECT id, embedding <=> (SELECT embedding FROM vector_chunks WHERE collection='fitness_knowledge' LIMIT 1) AS dist
FROM vector_chunks WHERE collection = 'fitness_knowledge' ORDER BY dist LIMIT 5;      -- first row dist ~ 0
```

### 4.5 Cut over

1. Deploy Core and Documents with `VECTOR_STORE_BACKEND=pgvector`, `EMBEDDING_PROVIDER=remote`.
2. Smoke-test retrieval (ask a question that should hit a document) and an upload.
3. **Keep the Chroma directory and its backup.** Do not delete Chroma until you have run on
   pgvector long enough to be confident (suggestion: at least a week), and then only as your own
   deliberate action; nothing in this repository deletes it.

### 4.6 Rollback of the cut-over

Set `VECTOR_STORE_BACKEND=chroma` (and, if you also moved embeddings, `EMBEDDING_PROVIDER=local`)
and redeploy the legacy image. Chroma was never modified, so it is exactly as before. Documents
uploaded *after* the cut-over exist only in pgvector/Supabase Storage; re-run
`migrate_chroma_to_pgvector.py` in reverse is not provided, so re-upload or re-ingest those.

## 5. What was proven (and what was not)

Proven, against a disposable Postgres 16 + pgvector container with Chroma's real ONNX model
(`tests/unit/deploy/test_chroma_pgvector_parity.py`):

* migration script copies all three collections, reports matching counts, is idempotent;
* stored dimension is 384 and equals what the embedder produces;
* for four natural-language queries the **ranked ids are identical** and cosine **distances agree
  to 1e-4** between `VectorStore` (Chroma) and `PgVectorStore`;
* owner scoping and metadata filtering (`$and`, equality, `$in`, comparisons) behave the same;
  unknown operators raise instead of silently widening results;
* the real migration chain runs on Postgres and downgrades cleanly.

Not proven (needs your credentials): that your chosen **remote** embedding provider returns vectors
equivalent to the local ONNX model - hence step 4.2 - and the Supabase Storage / Supabase-hosted
Postgres integration.
