# Architecture and consistency

## Storage and responsibilities

| Layer | Implementation | Persistent output |
| --- | --- | --- |
| Ingestion | `ingestion/client.py`, `runner.py`, `window.py` | Immutable `data/bronze/ted/` runs/pages and manifests |
| Normalization | `processing/silver.py`, `silver_run.py`, `quality.py` | Run-specific `data/silver/ted/` Parquet and validation metadata |
| Persistence | `database/silver_loader.py` | `silver.tenders`, keyed by `publication_number` |
| Embeddings | `search/embedding_refresh.py`, `vector.py` | `search.tender_embeddings`, keyed by notice and model |
| Analytics | `dbt/models` | Staging plus buyer, country/day and CPV marts |
| Serving | `search/service.py`, `rag/pipeline.py`, `api/app.py` | Search, grounded answers and browser workspace |
| Operations | `pipeline/operational.py`, `audit.py`, `status.py` | `data/refresh/<refresh_id>/refresh_audit.json` |

Run-specific Parquet files are incoming batches. They are not a merged export of
the complete database. PostgreSQL holds the accumulated Silver dataset.

## Incremental transaction boundary

The loader validates incoming data, copies it into a temporary staging table,
serializes Silver writers, classifies insert/update/no-change, and UPSERTs inside
one PostgreSQL transaction. Material equality excludes ingestion metadata. An
unchanged notice retains its prior `ingestion_run_id`, enabling durable vector
freshness checks. No normal refresh deletes notices absent from its window.

Embedding and dbt stages commit separately. The entire multi-stage refresh is
**not one atomic transaction**. A failed embedding or dbt stage may leave a valid
Silver update committed. The audit records failure rather than claiming rollback.
Audits use atomic file replacement; that is distinct from database atomicity.

## Embedding recovery

For each configured-model vector, compare its `ingestion_run_id` with Silver.
Missing or mismatched vectors are regenerated and UPSERTed, grouped by source
run. Current vectors do not load the encoder or call inference. The same model
instance is reused across repair groups in one attempt.

This also repairs a previous failure after Silver committed: correctness no longer
depends only on the *current* run's inserted/updated list. Successful groups survive
a later group's failure and are skipped on retry. `make repair-embeddings` exposes
the same recovery without fetching TED. A code/model revision with unchanged model
name is not detected automatically; document and plan a deliberate vector migration.

Run only one refresh/repair process at a time. Silver's lock serializes its loader,
but it is not a lock across ingestion, encoding and dbt. This is a single-operator
pipeline, not a distributed scheduler. Search may see temporarily stale vectors
between stages or after a failure; resolve failed refreshes before relying on results.

## Retrieval and generation

Lexical retrieval uses PostgreSQL's `simple` text-search configuration with weighted
fields; it is not language-specific stemming. Semantic retrieval uses normalized
384-dimensional `intfloat/multilingual-e5-small` vectors. Weighted RRF combines ranks,
not raw lexical and cosine scores. The existing settings are frozen for this update.

The RAG pipeline assigns evidence IDs, applies a character budget, generates via
the server-configured provider and validates the selected citations. It does not
prove every generated assertion. The browser treats evidence text as text and
restricts source links to HTTPS TED URLs.

## Operational boundaries

`/health` checks database connectivity, not TED freshness, complete table coverage
or Ollama responsiveness. `/operations/status` reads local audit files; its counts
are the last known successful counts, not fresh database queries. A zero-result
success can advance the known date while carrying prior known counts. The latest
window end is not proof of continuous coverage of all earlier dates/countries.
A process killed abruptly can leave a `running` audit; inspect the process before
assuming it remains active. Corrupt audit input produces a sanitized status error.
