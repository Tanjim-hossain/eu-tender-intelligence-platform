# Operations runbook

## Daily use

Run from the repository root with the existing `.env`. Keep `POSTGRES_DB=tendergraph`.
The supported buyer-country scope is BEL, NLD, DEU and ITA; the CLI validates code
syntax, while Silver validation enforces that scope.

```bash
make db-up
make db-health
make refresh START_DATE=2026-09-25 END_DATE=2026-09-26 COUNTRIES="BEL NLD DEU ITA"
make scheduled-refresh
curl -fsS http://127.0.0.1:8000/operations/status
```

Publication dates are inclusive. Scheduler dates use UTC; launchd's 08:30 execution
time uses the Mac's local time. The three-day overlap helps catch recent updates,
but cannot guarantee capture of corrections to much older notices. Backfill wider
windows explicitly when needed. Do not run concurrent manual and scheduled jobs.

A macOS launchd example is included for optional daily refresh scheduling.
If the job is installed locally, its current state can be inspected with:

```bash
launchctl print "gui/$(id -u)/com.tanjim.tendergraph.refresh"
```

For a new Mac, use the example in `infra/com.tanjim.tendergraph.refresh.plist.example`:
replace both absolute-path placeholders, create the log directory, validate with
`plutil -lint`, and install it only when you want to activate scheduling. The
repository does not modify the local LaunchAgents directory automatically.

## Failure recovery

| Failure | Action |
| --- | --- |
| TED fetch / Silver validation | Inspect failed audit and Bronze manifest; fix the cause, rerun the same window |
| Silver transaction | Existing committed dataset remains; fix input/connection, rerun |
| Encoder / vector write | Restore model access, use `make repair-embeddings`, then dbt build; or rerun a non-empty window |
| dbt build | Inspect dbt logs/results, fix cause and rerun dbt or the refresh |
| Scheduled wrapper | Inspect stdout/stderr and exit code; check Docker, PATH and `.env` |
| Stale/unknown operations status | Check audit mount/path, last successful window and scheduled job |

```bash
make repair-embeddings
uv run --frozen --env-file .env dbt build --project-dir dbt --profiles-dir dbt
```

Repair changes vectors only; it does not write a completed TED refresh audit. A full
successful refresh is needed to advance `/operations/status`. A zero-match refresh
intentionally does no Silver/vector work and cannot repair old missing vectors.
Failure audits/logs can contain raw exception details: keep them private.

## Read-only data-quality check

```bash
docker compose --env-file .env -f infra/compose.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT count(*) AS silver_rows FROM silver.tenders;
SELECT count(*) AS embedding_rows FROM search.tender_embeddings;
SELECT count(*) AS missing_or_stale
FROM silver.tenders s LEFT JOIN search.tender_embeddings e
  ON e.publication_number = s.publication_number
 AND e.model_name = 'intfloat/multilingual-e5-small'
WHERE e.publication_number IS NULL
   OR e.ingestion_run_id IS DISTINCT FROM s.ingestion_run_id;
SELECT count(*) AS orphan_embeddings
FROM search.tender_embeddings e LEFT JOIN silver.tenders s
  USING (publication_number)
WHERE s.publication_number IS NULL;
SQL
```

The overall embedding count may include multiple models. Use the model-specific
missing/stale check as well. Normal refresh never purges historical rows or orphans;
a deletion policy needs separate review and backups.

## Backup and stop safely

```bash
mkdir -p data/backups
docker compose --env-file .env -f infra/compose.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "data/backups/tendergraph-$(date +%Y%m%d-%H%M%S).dump"
```

Check that backup succeeded before relying on it. Keep an off-machine copy and test
restoration in a separate database before production use. To pause the database,
use `docker compose --env-file .env -f infra/compose.yml stop postgres`. Preserve
the named volume. Repository files do not back up the database or installed model weights.
