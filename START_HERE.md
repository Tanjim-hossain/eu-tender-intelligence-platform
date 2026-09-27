# Apply the Phase E5 update

This source update continues handoff commit `f8bbe1e`. Incremental ingestion,
scheduling, UI and operational status already existed. See `WORK_UPDATE.md` for
the new recovery fix, packaging and documentation changes.

## Existing Mac repository — recommended patch route

Keep `.env`, `data`, the PostgreSQL Docker volume, Ollama models and Git history.
Do not pop old stashes. Extract the ZIP separately. The `patches/` folder next to
this project contains only the delivery commits after the handoff snapshot.

```bash
cd ~/Projects/eu-tender-intelligence-platform
git status --short --branch
```

If your current working tree has edits, review and commit them first when ready;
do not overwrite them with the ZIP. With a clean working tree based on the handoff:

```bash
git switch -c feat/phase-e5-readiness
# Set this to the extracted handoff directory containing patches/.
TENDERGRAPH_HANDOFF="$HOME/Downloads/TenderGraph-Work-Handoff-20260927"
git am "$TENDERGRAPH_HANDOFF"/patches/*.patch
```

If Git reports a conflict, inspect it before continuing. Do not reset your repository
or use a force-copy workaround. The patches preserve the real pre-handoff history;
the ZIP's source snapshot is also included for inspection or a fresh checkout.

## Verify and demo

```bash
uv sync --frozen
make check
make package
make db-up
make db-health
make serve
```

With your existing `.env`, Ollama remains the configured provider. Open
http://127.0.0.1:8000, search `hospital information system`, ask a focused question,
and inspect its source links. No initial reload or model reinstall is required.

```bash
# Separate terminal, same project folder:
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/operations/status
make evaluate-local
```

## Verify the recovery improvement against your database

```bash
make repair-embeddings
```

A healthy corpus should report zero embedded rows. If old failures left missing
or stale vectors, only those are regenerated. This command does not fetch TED or
replace Silver data. Use the read-only count/freshness queries and dbt command in
`docs/OPERATIONS.md` to verify the result. Run it while the scheduled refresh is idle.

## Optional container / publication

Native Mac + Ollama remains the primary demo. For evidence-only API packaging,
see `docs/DEPLOYMENT.md`: `make app-build`, then `make app-up`. Image build and hosted
GitHub Actions still need execution on your machine/GitHub. No deployment or paid
service was activated. The existing launchd job can continue at the same repo path.
