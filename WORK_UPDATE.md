# Work update — 26 September 2026

## Completed milestone

Connected the existing retrieval and RAG components through `POST /ask`.
The original archive already contained 80 passing tests, an OpenAI provider,
prompt/context construction, and citation validation, but no answer endpoint.

Changes:

- Added retrieval-to-evidence orchestration, optional cross-encoder reranking,
  and citation IDs assigned after final ranking.
- Added a free, non-generative evidence mode as the default. Its output is
  explicitly labelled as retrieved facts rather than a generated answer.
- Added an optional local Ollama provider with bounded output, timeout handling,
  and explicit model configuration. No paid fallback or automatic retries.
- Connected the existing OpenAI adapter as an explicit server-side opt-in,
  with timeout, incomplete-output handling, and resource cleanup.
- Added `/ask` request/response validation, source metadata, no-results handling,
  sanitized provider/database errors, and a command-line client.
- Added context size controls, disclosed truncation, and duplicate citation checks.
- Restored a credential-free `.env.example` and wrote setup/continuation instructions
  in the previously empty README.

## Verified here

- Installed the uploaded lockfile with `uv sync --frozen`.
- Original suite: **80 passed**.
- Updated suite: **122 passed** (42 additional test cases).
- `ruff check .`: passed.
- `mypy src scripts`: passed, 64 source files.
- CLI help loads successfully.
- API tests exercise the actual `/ask` endpoint and answer pipeline with injected
  retrieval/evidence fixtures. Ollama HTTP behavior uses a mock transport.
- Tests cover citation/source mapping, reranking order, no-results behavior,
  context limits, invalid generations, malformed requests, timeout/HTTP failures,
  and the default mode never constructing an LLM client.

## Not verified here

This environment has no running PostgreSQL/pgvector or Ollama daemon. No live
database retrieval, local model generation, or paid OpenAI call was made. The
new tests do not establish real answer quality, model latency, or factual
entailment. Existing retrieval evaluation files were preserved without rerunning
or changing their reported metrics.

## Run against your existing Mac database

Retain your existing `.env`. From the updated project directory:

```bash
uv sync --frozen
docker compose --env-file .env -f infra/compose.yml up -d
RAG_PROVIDER=evidence uv run --frozen uvicorn tendergraph.api.app:app --host 127.0.0.1 --port 8000
```

In another terminal, from the same directory:

```bash
uv run --frozen python scripts/ask_tenders.py \
  "Who is the buyer and what deadline is stated?" \
  --query "hospital information system" --limit 3
```

Expected behavior: `Mode: evidence | Status: evidence_only`, followed by retrieved
facts and source links. Inspect <http://127.0.0.1:8000/docs> for the full schema.
No database reload is required. See the README for local Ollama configuration.

This completes the API/RAG integration milestone, not the entire product roadmap.
The next step is a live smoke test on the existing Mac setup, then answer-quality
evaluation before building and deploying a user-facing application.
