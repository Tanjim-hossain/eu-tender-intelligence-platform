# Phase E5 delivery — 27 September 2026

## Starting point

The supplied source ZIP identifies main commit `f8bbe1e` and includes completed
incremental refresh, zero-result handling, scheduling and `/operations/status`.
It contains no original Git database. Work was tracked on a separate local
`work/phase-e5` branch from an unchanged source snapshot; delivery patches exclude
that snapshot commit and apply onto the user's existing history.

The initial source passed Ruff, mypy (82 source files), 208 tests and 14/14 offline
answer-contract cases here. The previous WORK_UPDATE described an older milestone;
it has been replaced by this account of the current delivery.

## Changes

1. **Partial-refresh recovery:** fixed a concrete failure mode where Silver could
   commit, embedding generation fail, and retry classify notices as unchanged and
   skip their embeddings. Non-empty refreshes now reconcile absent/stale vectors
   using per-notice ingestion run IDs, grouped by source run. Existing current
   vectors are skipped. Added `make repair-embeddings` for recovery without TED.
2. **Operational fixes:** database URI components escape reserved characters in
   credentials/database names; the scheduler prints its completion/exit footer even
   when refresh fails, retaining the original nonzero exit code.
3. **Packaging:** added a multi-stage non-root API Dockerfile, restricted build
   context, loopback-bound opt-in evidence-mode Compose overlay and package asset
   verifier. Existing PostgreSQL volume/project and native Ollama setup are preserved.
4. **CI:** retained deterministic quality checks, expanded push coverage, disabled
   model downloads during checks and added wheel/asset and API image import checks.
   No model, TED or database service is required for those test steps.
5. **Reproducibility and portfolio:** rewrote README and start instructions, added
   architecture, operations/recovery, benchmark provenance and deployment assessment,
   included a launchd example, and added a read-only historical-metric summarizer.
   The example native configuration selects local Ollama; no provider code default
   or existing user `.env` was changed. Production ranking is unchanged.

## Executed verification

- Fresh `uv sync --frozen` from the supplied lockfile succeeded.
- Final `ruff check .`: passed.
- Final `mypy src scripts`: passed, **85 source files**.
- Final `pytest -q`: **215 passed** (208 baseline + 7 regressions).
- Offline answer-contract replay: **14/14 passed**.
- Targeted recovery/embedding/refresh/zero-result tests: **20 passed**.
- Real scheduler shell wrapper tested with stubbed executables for exit 0 and 7.
- Source distribution and wheel built; HTML/CSS/JS package assets verified.
- Wheel installed into a separate environment with only locked runtime dependencies;
  API import, `/`, JS, CSS, OpenAPI and uninitialized `/config` behavior passed.
  No dbt/dev dependencies, database connection or model download were needed.
- Shell syntax, YAML parsing and launchd XML/plist parsing passed.
- Refresh and scheduler CLI help executed successfully.
- Historical metric aggregation reproduced README table from committed TSVs.
- `git diff --check`: passed. See `docs/verification.txt` for final quality output.

## Limits and remaining environment gates

No Docker executable/daemon, PostgreSQL server or Ollama daemon is available here.
The container image was not built or started. Compose was parsed as YAML, not
validated by a running Docker stack. No live SQL, model generation, TED refresh,
launchd installation, browser re-run, or hosted CI was performed in this delivery.
The UI is unchanged; retained screenshots are earlier synthetic fixtures.

The supplied handoff reports 5,819 Silver rows, 5,819 vectors, zero missing/orphan
vectors and successful scheduled execution. These remain historical handoff facts.
Recovery tests use fixtures, not real PostgreSQL. After applying, run the read-only
SQL and local smoke checks in `docs/OPERATIONS.md` before declaring the updated
pipeline live-verified. The pipeline commits stages separately and must run serially.

No Git remote was supplied/configured, so there is no hosted GitHub Actions result.
No cloud service, public endpoint, paid model call or deployment was created. The
repository is prepared for publication and a local portfolio demo; Docker runtime,
hosted CI and public deployment readiness remain separate verification gates.
