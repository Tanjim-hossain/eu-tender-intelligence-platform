# TenderGraph — Work Handoff

## Repository state

- Repository: eu-tender-intelligence-platform
- Stable branch: main
- Handoff commit: f8bbe1e
- Python: 3.12
- Package: tendergraph
- Local PostgreSQL: PostgreSQL 16 + pgvector
- Current full test suite: 208 passed
- Answer contract replay: 14/14 passed

## Project goal

TenderGraph is a production-oriented European public procurement intelligence platform built from official TED procurement data.

Current architecture:

TED Search API
→ immutable Bronze ingestion
→ enriched Silver normalization and validation
→ PostgreSQL / pgvector
→ dbt analytics marts
→ lexical + semantic + weighted-RRF hybrid retrieval
→ FastAPI
→ grounded RAG
→ web UI
→ incremental refresh / scheduling / operational monitoring

Target countries currently:
BEL, NLD, DEU, ITA.

## Major completed work

### Data ingestion and transformation

- Official TED Search API ingestion.
- Immutable Bronze page/run artifacts and manifests.
- Enriched Silver tender normalization.
- Quality validation and duplicate/out-of-scope checks.
- Run-specific Silver Parquet artifacts.
- PostgreSQL persistence.
- dbt staging and analytics marts.

### Retrieval and AI

- Lexical retrieval.
- Semantic retrieval using intfloat/multilingual-e5-small.
- pgvector embeddings.
- Weighted Reciprocal Rank Fusion hybrid search.
- Evaluated retrieval baseline showed hybrid retrieval outperforming lexical and semantic alone.
- Grounded answer pipeline.
- Evidence-only mode.
- Local Ollama support using qwen3:4b-instruct.
- FastAPI /search and /ask endpoints.
- Web UI.

### Incremental refresh

Completed production-style incremental pipeline:

TED date-window ingestion
→ Bronze
→ Silver
→ publication_number UPSERT
→ detect inserted/updated/unchanged
→ regenerate embeddings only for changed tenders
→ dbt build
→ atomic refresh audit

CLI:

uv run --frozen --env-file .env python scripts/refresh_tenders.py \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --countries BEL NLD DEU ITA

Verified live behavior:

- Initial DB after incremental refresh: 5819 Silver tenders.
- Embedding rows: 5819.
- Missing embeddings: 0.
- Orphan embeddings: 0.
- Incremental reruns are idempotent.
- Changed tenders regenerate only changed embeddings.

### Zero-result handling

TED windows with zero matches are valid successful no-op refreshes.

Behavior:

0 TED notices
→ completed Bronze run
→ no Silver artifact
→ no DB mutation
→ no embedding generation
→ dbt validation
→ completed audit
→ CLI success

Live zero-result scenario was verified.

### Operations

Make targets include:

- install
- check
- serve
- evaluate
- evaluate-local
- db-up
- db-health
- refresh
- scheduled-refresh

macOS scheduled refresh is implemented with:

- 3-day trailing overlapping window
- default end date = UTC yesterday
- Docker/PostgreSQL readiness checks
- local launchd scheduling
- logging

Machine-level launchd job was installed as:

com.tanjim.tendergraph.refresh

Schedule:
daily at 08:30 local Mac time.

Background launchd execution was verified with exit code 0.

### Operational status

Existing /health remains DB-readiness focused.

New endpoint:

GET /operations/status

It exposes:

- overall status
- latest refresh ID/status
- latest refresh window
- last successful refresh
- expected data-through date
- lag days
- stale flag
- latest known Silver DB row count
- latest known embedding row count
- dbt status
- failure stage/type

Current verified local status at handoff:

overall_status=ok
latest_refresh_status=completed
latest_window_end=2026-09-26
expected_data_through=2026-09-26
lag_days=0
stale=False
last_success_database_rows=5819
last_success_embedding_rows=5819

### CI and quality

GitHub Actions workflow exists:

.github/workflows/ci.yml

It runs the project quality gate through make check.

Important:
No Git remote is configured yet, therefore hosted GitHub Actions execution has NOT yet been verified.

Current local quality gate:

- Ruff clean
- mypy clean across 82 source files
- pytest: 208 passed
- answer contract replay: 14/14 passed

## Important operational constraints

- Use `uv run python`, not plain `python`.
- Do not commit `.env`.
- Do not remove PostgreSQL Docker volumes.
- Do not use `docker compose down -v`.
- Do not publicly expose the FastAPI app yet without auth/rate limiting/security review.
- Local audit/data artifacts are intentionally ignored by Git.
- Do not unnecessarily re-open completed incremental/scheduler work.
- Avoid feature creep.

## Remaining work — Phase E5

The project is now entering final deployment/readiness and portfolio-polish work.

Recommended remaining sequence:

1. Deployment/readiness inventory.
2. Decide whether API containerization/deployment files are genuinely needed.
3. Review `.env.example`, runtime configuration and reproducibility.
4. Improve README:
   - concise project proposition
   - architecture
   - setup
   - ingestion/refresh workflow
   - retrieval methodology
   - benchmark/results table
   - RAG/evidence behavior
   - operations/scheduler
   - API endpoints
   - limitations/security
5. Add or improve architecture diagram where useful.
6. Document evaluation results and live incremental-refresh evidence.
7. Connect GitHub remote when user is ready.
8. Push and verify real GitHub Actions CI.
9. Run final clean-room/reproducibility audit.
10. Final repository/portfolio review and optionally create release/tag-ready state.

Cloud deployment should be treated separately from local production-style readiness.
Do not claim hosted/cloud production readiness unless actually deployed and verified.

## Working style requested by user

- Continue from current state; do not restart the project.
- Work autonomously in Work/agentic mode where possible.
- Inspect repository before making changes.
- Prefer production-quality engineering over unnecessary features.
- Preserve verified behavior.
- Run tests after modifications.
- Never claim success without execution evidence.
- Keep commits logically scoped.
- Complete the remaining project rather than stopping after planning.
