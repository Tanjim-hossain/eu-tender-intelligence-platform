# Continue from your existing Mac project

This update adds a browser workspace, stricter evidence selection, and answer
evaluation. It is source code only. Reuse your current `.env`, data directory,
PostgreSQL volume, installed Ollama model, and Git history. No database reload or
schema migration is needed.

## 1. Merge the source update

Stop the existing API with Ctrl+C. Unzip this archive into a **separate** folder.
Set the first path below to the extracted `eu-tender-intelligence-platform` folder.
Run from Terminal:

```bash
TENDERGRAPH_UPDATE="$HOME/Downloads/TenderGraph-Latest-20260927-010932/eu-tender-intelligence-platform"
TENDERGRAPH_PROJECT="$HOME/Projects/eu-tender-intelligence-platform"
test -f "$TENDERGRAPH_UPDATE/START_HERE.md" && test -d "$TENDERGRAPH_PROJECT/src" && \
rsync -av --exclude='.env' --exclude='.git/' --exclude='.venv/' \
  --exclude='data/' --exclude='__pycache__/' \
  "$TENDERGRAPH_UPDATE/" "$TENDERGRAPH_PROJECT/"
```

Adjust the paths if Finder extracted the ZIP differently. This copies source
files over their existing versions without deleting unrelated files. Your local
credentials and data are excluded. The `.env.example` file is only a template;
do not copy it over your working `.env`.

## 2. Start the workspace

```bash
cd ~/Projects/eu-tender-intelligence-platform
uv sync --frozen
docker compose --env-file .env -f infra/compose.yml up -d
uv run --frozen uvicorn tendergraph.api.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Existing `.env` settings choose the answer mode. For
your local AI setup, leave Ollama running with your installed `qwen3:4b-instruct`.
Use a search topic, inspect results, and ask a focused question. The answer shows
only the sources selected as relevant, or an insufficient-evidence message.

## 3. Check local model behavior

From another terminal in the same project:

```bash
uv run --frozen python scripts/evaluate_answers.py --live
```

This calls only local Ollama on six synthetic cases, not your database. Review
`evaluation/answers/reports/local_model.json`, including each case's manual review
criterion. A selection/format pass alone does not prove the answer is factually
correct. See `WORK_UPDATE.md` for completed checks and remaining work.
