from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.ingestion.client import TedClient
from tendergraph.pipeline.audit import (
    DEFAULT_REFRESH_AUDIT_ROOT,
    RefreshAuditRecord,
    new_refresh_audit,
    write_refresh_audit,
)
from tendergraph.pipeline.dbt import (
    DEFAULT_DBT_PROFILES_DIR,
    DEFAULT_DBT_PROJECT_DIR,
    DbtBuildSummary,
    run_dbt_build,
)
from tendergraph.pipeline.refresh import (
    IncrementalRefreshSummary,
    RefreshStage,
    run_incremental_refresh,
)
from tendergraph.processing.silver_run import (
    DEFAULT_SILVER_RUN_ROOT,
)
from tendergraph.search.embedding_refresh import (
    SentenceEncoder,
)
from tendergraph.storage.iteration_run import (
    IterationRunWriter,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class OperationalRefreshSummary:
    refresh: IncrementalRefreshSummary
    dbt: DbtBuildSummary
    audit_path: Path

    @property
    def refresh_id(self) -> str:
        return self.audit_path.parent.name

    @property
    def run_id(self) -> str:
        return self.refresh.run_id


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _finished_timestamp(
    clock: Clock,
) -> str:
    timestamp = clock()

    if timestamp.tzinfo is None:
        raise ValueError(
            "clock must return timezone-aware datetime"
        )

    return timestamp.astimezone(
        UTC
    ).isoformat()


def _completed_audit(
    running: RefreshAuditRecord,
    *,
    refresh: IncrementalRefreshSummary,
    dbt: DbtBuildSummary,
    finished_at_utc: str,
) -> RefreshAuditRecord:
    ingestion = refresh.ingestion
    embeddings = refresh.embeddings

    if refresh.no_data:
        return replace(
            running,
            status="completed",
            finished_at_utc=finished_at_utc,
            ingestion_run_id=refresh.run_id,
            bronze_source_matches=(
                ingestion.total_source_matches
            ),
            bronze_records_retrieved=(
                ingestion.records_retrieved
            ),
            bronze_unique_notices=(
                ingestion.unique_publication_numbers
            ),
            bronze_duplicate_notices=(
                ingestion.duplicate_publication_numbers
            ),
            silver_rows=0,
            inserted_rows=0,
            updated_rows=0,
            unchanged_rows=0,
            changed_publication_numbers=(),
            embedding_requested_rows=0,
            embedding_embedded_rows=0,
            embedding_inserted_rows=0,
            embedding_updated_rows=0,
            embedding_database_rows=None,
            dbt_success=dbt.success,
            dbt_elapsed_seconds=(
                dbt.elapsed_seconds
            ),
            dbt_result_type=dbt.result_type,
        )

    silver = refresh.silver_artifact
    load = refresh.silver_load

    if silver is None or load is None:
        raise RuntimeError(
            "Non-empty refresh is missing "
            "Silver load artifacts"
        )

    return replace(
        running,
        status="completed",
        finished_at_utc=finished_at_utc,
        ingestion_run_id=refresh.run_id,
        bronze_source_matches=(
            ingestion.total_source_matches
        ),
        bronze_records_retrieved=(
            ingestion.records_retrieved
        ),
        bronze_unique_notices=(
            ingestion.unique_publication_numbers
        ),
        bronze_duplicate_notices=(
            ingestion.duplicate_publication_numbers
        ),
        silver_parquet_path=str(
            silver.parquet_path
        ),
        silver_sha256=silver.sha256,
        silver_rows=silver.row_count,
        inserted_rows=load.inserted_rows,
        updated_rows=load.updated_rows,
        unchanged_rows=load.unchanged_rows,
        database_rows=load.database_rows,
        changed_publication_numbers=(
            load.changed_publication_numbers
        ),
        embedding_requested_rows=(
            embeddings.requested_rows
        ),
        embedding_embedded_rows=(
            embeddings.embedded_rows
        ),
        embedding_inserted_rows=(
            embeddings.inserted_rows
        ),
        embedding_updated_rows=(
            embeddings.updated_rows
        ),
        embedding_database_rows=(
            embeddings.database_rows
        ),
        dbt_success=dbt.success,
        dbt_elapsed_seconds=(
            dbt.elapsed_seconds
        ),
        dbt_result_type=dbt.result_type,
    )


def run_operational_refresh(
    *,
    start_date: date,
    end_date: date,
    countries: Sequence[str],
    settings: DatabaseSettings | None = None,
    silver_root: Path = DEFAULT_SILVER_RUN_ROOT,
    audit_root: Path = DEFAULT_REFRESH_AUDIT_ROOT,
    dbt_project_dir: Path = DEFAULT_DBT_PROJECT_DIR,
    dbt_profiles_dir: Path = DEFAULT_DBT_PROFILES_DIR,
    client: TedClient | None = None,
    writer: IterationRunWriter | None = None,
    encoder: SentenceEncoder | None = None,
    embedding_batch_size: int = 32,
    clock: Clock = _utc_now,
) -> OperationalRefreshSummary:
    """Run incremental refresh, dbt build, and audit lifecycle."""

    started_at = clock()

    if started_at.tzinfo is None:
        raise ValueError(
            "clock must return timezone-aware datetime"
        )

    running = new_refresh_audit(
        start_date=start_date,
        end_date=end_date,
        countries=tuple(countries),
        started_at=started_at,
    )

    audit_path = write_refresh_audit(
        running,
        root=audit_root,
    )

    current_stage: str = "incremental_refresh"

    def mark_stage(
        stage: RefreshStage,
    ) -> None:
        nonlocal current_stage
        current_stage = stage

    try:
        refresh = run_incremental_refresh(
            start_date=start_date,
            end_date=end_date,
            countries=countries,
            settings=settings,
            silver_root=silver_root,
            client=client,
            writer=writer,
            encoder=encoder,
            embedding_batch_size=(
                embedding_batch_size
            ),
            on_stage_start=mark_stage,
        )

        current_stage = "dbt"

        dbt = run_dbt_build(
            project_dir=dbt_project_dir,
            profiles_dir=dbt_profiles_dir,
        )

        completed = _completed_audit(
            running,
            refresh=refresh,
            dbt=dbt,
            finished_at_utc=(
                _finished_timestamp(
                    clock
                )
            ),
        )

        audit_path = write_refresh_audit(
            completed,
            root=audit_root,
        )

    except Exception as exc:
        failed = replace(
            running,
            status="failed",
            finished_at_utc=(
                _finished_timestamp(
                    clock
                )
            ),
            failure_stage=current_stage,
            failure_type=type(
                exc
            ).__name__,
            failure_message=str(
                exc
            ),
        )

        write_refresh_audit(
            failed,
            root=audit_root,
        )

        raise

    return OperationalRefreshSummary(
        refresh=refresh,
        dbt=dbt,
        audit_path=audit_path,
    )
