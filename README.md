# TenderGraph — European Tender Intelligence

TenderGraph ingests TED procurement notices, normalizes them into a typed Silver
dataset, and combines PostgreSQL full-text search with multilingual semantic
retrieval. It exposes search and evidence-backed question answering through FastAPI.

Built by Tanjim Hossain. Python 3.12+, PostgreSQL 16 with pgvector, Polars, dbt,
Sentence Transformers, and FastAPI.

## Current capabilities

- TED pagination, retry handling, Bronze manifests, and normalized Silver data.
- PostgreSQL loading, typed amounts/deadlines, and dbt analytical marts.
- Lexical and multilingual-e5-small vector retrieval with weighted reciprocal rank fusion.
- Optional multilingual cross-encoder reranking using the existing evaluation model.
- `POST /search` for ranked notices; `POST /ask` for source evidence or generated answers.
- Stable citation IDs linked to actual retrieved notices and TED source URLs.
- No-generation default; optional local Ollama or explicitly configured OpenAI generation.

## Continue with the existing Mac setup

Keep your current `.env`, Docker volume, and Git history. Merge the updated source
into your existing project folder, or run the extracted folder alongside it after
copying your existing `.env` there. Do not replace your password with the example
value. This update does not require a database reload or schema migration.

From the project root:

```bash
uv sync --frozen
docker compose --env-file .env -f infra/compose.yml up -d
RAG_PROVIDER=evidence uv run --frozen uvicorn tendergraph.api.app:app --host 127.0.0.1 --port 8000
```

The shell override explicitly keeps this run in free evidence mode even if another
provider is configured in `.env`. Start a second terminal in the same project:

```bash
uv run --frozen python scripts/ask_tenders.py \
  "Who is the buyer and what deadline is stated?" \
  --query "hospital information system" --limit 3
```

Interactive API documentation: <http://127.0.0.1:8000/docs>.
You can call `/ask` there without using the CLI.

## Answer modes

| `RAG_PROVIDER` | Behavior | Generation requirements |
| --- | --- | --- |
| `evidence` (default) | Returns retrieved facts and source links, labelled `evidence_only` | No LLM, no API key |
| `ollama` | Generates an answer using a local model and checks citation IDs | Local Ollama daemon and an explicitly selected installed model |
| `openai` | Uses the existing Responses API provider and checks citation IDs | Explicit model and API credentials; usage can incur charges |

Evidence mode is a retrieval report, **not** an AI-written answer. Search matches
are not a guarantee of suitability or eligibility. The retrieval encoder still
runs locally; its model weights must be present or downloaded on first startup.

### Local generation with Ollama

Install and start Ollama, download a model suitable for your machine, and use
`ollama list` to find its exact local tag. Put these values in `.env`:

```dotenv
RAG_PROVIDER=ollama
RAG_MODEL=your-installed-local-model-tag
RAG_OLLAMA_URL=http://127.0.0.1:11434
RAG_MAX_OUTPUT_TOKENS=800
RAG_TIMEOUT_SECONDS=120
```

Replace the model placeholder, then restart the API **without** the evidence-mode
shell override:

```bash
uv run --frozen uvicorn tendergraph.api.app:app --host 127.0.0.1 --port 8000
```

This adapter calls the loopback daemon's
[`POST /api/generate`](https://docs.ollama.com/api/generate) endpoint with streaming
disabled. Model installation is a separate step; this project never pulls a model
on your behalf. Use a local model, not an Ollama cloud-backed model. Inference
uses your computer's memory and processing resources.

### Optional paid generation

Set `RAG_PROVIDER=openai`, `RAG_MODEL` to a model available to your API account, and
`OPENAI_API_KEY` in `.env`, then restart the API. The application never changes
providers automatically. Merely having an API key present does not enable paid
generation. The `/ask` payload cannot override the server's provider or model.
There are no automatic generation retries or fallback to a paid provider.

### Optional reranking

Set `RAG_RERANK=true` and restart to score retrieved candidates with the existing
cross-encoder before selecting evidence. Default is false: the uploaded evaluation
showed mixed metric changes and extra latency. Enabling it may download another
model on first startup. Reranking does not call a paid generation API.

## API contract

```bash
curl -sS http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Who is the buyer?","query":"cloud platform","evidence_limit":3,"retrieval_depth":20}'
```

`question` is required. `query` optionally gives retrieval a short topic phrase;
otherwise the question is the retrieval query. `evidence_limit` is 1–10 and
`retrieval_depth` is at least that limit, at most 100.

The response includes `answer`, `mode`, `status`, `citations`, `sources`, and
`context_truncated`. `sources` maps citation IDs to publication numbers, buyer
details, deadlines, amounts, and source URLs. Missing values remain null in JSON
and “Not stated” in formatted evidence. Decimal amounts serialize as strings.

- `evidence_only`: retrieved facts, with no generated interpretation.
- `answered`: generated text passed citation-ID checks.
- `no_results`: retrieval returned no notices; the generator was not called.
- HTTP 422: invalid request, including an attempt to select a provider in the body.
- HTTP 502: generated answer failed citation validation or evidence cannot fit the budget.
- HTTP 503: the configured generator or database is unavailable.

Citation checks reject empty, uncited, or unknown-reference answers. They **do not
prove factual entailment** or that every claim is supported. Treat generated answers
as reviewable summaries and inspect the linked notices. The prompt treats tender
text as untrusted evidence, but prompting alone cannot eliminate prompt injection.
There is no calibrated relevance threshold or automatic eligibility decision.

Generated contexts use a character budget (`RAG_MAX_CONTEXT_CHARS`, default 40000).
Long descriptions are marked as truncated, and lower-ranked notices are omitted
if needed. `context_truncated` discloses this; returned sources match the context
actually sent. A character budget is not an exact model token limit. For a small
local context window, lower this setting and/or `evidence_limit`.

## Fresh database setup (only when needed)

The existing Mac database can be reused. For a new local database, copy
`.env.example` to `.env`, choose a password, start the Compose service, then:

```bash
uv run --frozen python scripts/load_silver_postgres.py data/silver/ted/tenders.parquet
uv run --frozen python scripts/search_tenders.py "cloud platform" --limit 1
uv run --frozen python scripts/load_semantic_embeddings.py
```

The first command reloads `silver.tenders`; do not run it merely to upgrade the API.
The second ensures the lexical column/index exists. The third uses the included
local semantic index; if that index is missing or stale, rebuild it first with
`scripts/build_semantic_index.py`. TED snapshots and embedding indexes must refer
to the same corpus. No ingestion or paid API call is required for this update.

## Verification and remaining work

```bash
uv run --frozen ruff check .
uv run --frozen mypy src scripts
uv run --frozen pytest -q
```

See `WORK_UPDATE.md` for this change's validation and limits. Original retrieval
evaluations remain in `evaluation/retrieval/`; this update does not claim new
retrieval quality or model accuracy results.

Next milestones: a live Mac smoke test of `/ask`; an answer-quality evaluation set
covering unsupported questions and citation entailment; then a user interface,
scheduled refresh, and deployment configuration. This local API has no authentication
or rate limiting and should not be exposed publicly as-is.
