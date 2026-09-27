import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from tendergraph.database.silver_loader import LoadSummary
from tendergraph.ingestion.runner import TedIngestionResult
from tendergraph.pipeline.dbt import DbtBuildSummary
from tendergraph.pipeline.operational import (
    run_operational_refresh,
)
from tendergraph.pipeline.refresh import (
    IncrementalRefreshSummary,
)
from tendergraph.processing.quality import (
    SilverQualitySummary,
)
from tendergraph.processing.silver_run import (
    SilverRunArtifact,
)
from tendergraph.search.embedding_refresh import (
    EmbeddingRefreshSummary,
)
from tendergraph.storage.iteration_run import (
    BronzeRunArtifact,
)

START = datetime(
    2026,
    9,
    27,
    17,
    0,
    tzinfo=UTC,
)

FINISH = datetime(
    2026,
    9,
    27,
    17,
    1,
    tzinfo=UTC,
)


class SequenceClock:
    def __init__(
        self,
        *values: datetime,
    ) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


def bronze(
    run_id: str = "run-1",
) -> BronzeRunArtifact:
    return BronzeRunArtifact(
        run_id=run_id,
        run_dir=Path(
            f"bronze/{run_id}"
        ),
        manifest_path=Path(
            f"bronze/{run_id}/"
            "run_manifest.json"
        ),
        page_count=1,
        record_count=2,
        status="completed",
    )


def ingestion(
    run_id: str = "run-1",
) -> TedIngestionResult:
    return TedIngestionResult(
        run_artifact=bronze(
            run_id
        ),
        query="example query",
        total_source_matches=2,
        records_retrieved=2,
        unique_publication_numbers=2,
        duplicate_publication_numbers=0,
    )


def silver_artifact(
    run_id: str = "run-1",
) -> SilverRunArtifact:
    return SilverRunArtifact(
        run_id=run_id,
        source_run_dir=Path(
            f"bronze/{run_id}"
        ),
        output_dir=Path(
            f"silver/{run_id}"
        ),
        parquet_path=Path(
            f"silver/{run_id}/"
            "tenders.parquet"
        ),
        row_count=2,
        sha256="a" * 64,
        quality=SilverQualitySummary(
            row_count=2,
            unique_publication_numbers=2,
            duplicate_publication_numbers=0,
            out_of_scope_rows=0,
            rows_with_deadlines=0,
            rows_with_estimated_value=0,
        ),
    )


def silver_load(
    *,
    inserted: tuple[str, ...] = (),
    updated: tuple[str, ...] = (),
) -> LoadSummary:
    return LoadSummary(
        parquet_rows=2,
        inserted_rows=len(
            inserted
        ),
        updated_rows=len(
            updated
        ),
        unchanged_rows=(
            2
            - len(inserted)
            - len(updated)
        ),
        database_rows=4885,
        inserted_publication_numbers=(
            inserted
        ),
        updated_publication_numbers=(
            updated
        ),
    )


def refresh_summary() -> IncrementalRefreshSummary:
    return IncrementalRefreshSummary(
        ingestion=ingestion(),
        silver_artifact=(
            silver_artifact()
        ),
        silver_load=silver_load(
            inserted=("A",),
            updated=("B",),
        ),
        embeddings=(
            EmbeddingRefreshSummary(
                requested_rows=2,
                embedded_rows=2,
                inserted_rows=1,
                updated_rows=1,
                database_rows=4885,
                ingestion_run_id="run-1",
            )
        ),
    )


def dbt_summary() -> DbtBuildSummary:
    return DbtBuildSummary(
        success=True,
        command=(
            "dbt",
            "build",
        ),
        elapsed_seconds=1.25,
        result_type=(
            "RunExecutionResult"
        ),
    )


def test_operational_refresh_writes_completed_audit(
    tmp_path: Path,
) -> None:
    clock = SequenceClock(
        START,
        FINISH,
    )

    with (
        patch(
            "tendergraph.pipeline.operational."
            "run_incremental_refresh",
            return_value=(
                refresh_summary()
            ),
        ),
        patch(
            "tendergraph.pipeline.operational."
            "run_dbt_build",
            return_value=(
                dbt_summary()
            ),
        ),
    ):
        summary = (
            run_operational_refresh(
                start_date=date(
                    2026,
                    9,
                    27,
                ),
                end_date=date(
                    2026,
                    9,
                    27,
                ),
                countries=["BEL"],
                audit_root=tmp_path,
                clock=clock,
            )
        )

    payload = json.loads(
        summary.audit_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "completed"
    assert (
        payload["ingestion_run_id"]
        == "run-1"
    )
    assert payload["inserted_rows"] == 1
    assert payload["updated_rows"] == 1
    assert (
        payload["embedding_requested_rows"]
        == 2
    )
    assert payload["dbt_success"] is True
    assert payload["failure_stage"] is None


def test_operational_refresh_records_core_failure_stage(
    tmp_path: Path,
) -> None:
    clock = SequenceClock(
        START,
        FINISH,
    )

    def fail_refresh(
        **kwargs: object,
    ) -> IncrementalRefreshSummary:
        callback = kwargs[
            "on_stage_start"
        ]

        assert callable(
            callback
        )

        callback(
            "silver_load"
        )

        raise ValueError(
            "database unavailable"
        )

    with (
        patch(
            "tendergraph.pipeline.operational."
            "run_incremental_refresh",
            side_effect=fail_refresh,
        ),
        patch(
            "tendergraph.pipeline.operational."
            "run_dbt_build"
        ) as dbt,pytest.raises(
        ValueError,
        match="database unavailable",
    )
    ):
        run_operational_refresh(
            start_date=date(
                2026,
                9,
                27,
            ),
            end_date=date(
                2026,
                9,
                27,
            ),
            countries=["BEL"],
            audit_root=tmp_path,
            clock=clock,
        )

    dbt.assert_not_called()

    audit_files = list(
        tmp_path.glob(
            "*/refresh_audit.json"
        )
    )

    assert len(
        audit_files
    ) == 1

    payload = json.loads(
        audit_files[0].read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "failed"
    assert (
        payload["failure_stage"]
        == "silver_load"
    )
    assert (
        payload["failure_type"]
        == "ValueError"
    )


def test_operational_refresh_records_dbt_failure(
    tmp_path: Path,
) -> None:
    clock = SequenceClock(
        START,
        FINISH,
    )

    with (
        patch(
            "tendergraph.pipeline.operational."
            "run_incremental_refresh",
            return_value=(
                refresh_summary()
            ),
        ),
        patch(
            "tendergraph.pipeline.operational."
            "run_dbt_build",
            side_effect=RuntimeError(
                "dbt build failed"
            ),
        ),pytest.raises(
        RuntimeError,
        match="dbt build failed",
    )
    ):
        run_operational_refresh(
            start_date=date(
                2026,
                9,
                27,
            ),
            end_date=date(
                2026,
                9,
                27,
            ),
            countries=["BEL"],
            audit_root=tmp_path,
            clock=clock,
        )

    audit_files = list(
        tmp_path.glob(
            "*/refresh_audit.json"
        )
    )

    assert len(
        audit_files
    ) == 1

    payload = json.loads(
        audit_files[0].read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "failed"
    assert (
        payload["failure_stage"]
        == "dbt"
    )
    assert (
        payload["failure_type"]
        == "RuntimeError"
    )
