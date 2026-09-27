import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tendergraph.cli.refresh import main as cli_main
from tendergraph.ingestion.runner import (
    TedIngestionResult,
    ingest_ted_window,
)
from tendergraph.pipeline.operational import (
    run_operational_refresh,
)
from tendergraph.pipeline.refresh import (
    IncrementalRefreshSummary,
    run_incremental_refresh,
)
from tendergraph.search.embedding_refresh import (
    EmbeddingRefreshSummary,
)
from tendergraph.storage.iteration_run import (
    BronzeRunArtifact,
)


def zero_bronze(
    run_id: str = "zero-run",
) -> BronzeRunArtifact:
    return BronzeRunArtifact(
        run_id=run_id,
        run_dir=Path(
            f"data/bronze/{run_id}"
        ),
        manifest_path=Path(
            f"data/bronze/{run_id}/"
            "run_manifest.json"
        ),
        page_count=1,
        record_count=0,
        status="completed",
    )


def zero_ingestion(
    run_id: str = "zero-run",
) -> TedIngestionResult:
    return TedIngestionResult(
        run_artifact=zero_bronze(
            run_id
        ),
        query="publication-date = 2026-09-27",
        total_source_matches=0,
        records_retrieved=0,
        unique_publication_numbers=0,
        duplicate_publication_numbers=0,
    )


def zero_refresh(
    run_id: str = "zero-run",
) -> IncrementalRefreshSummary:
    return IncrementalRefreshSummary(
        ingestion=zero_ingestion(
            run_id
        ),
        silver_artifact=None,
        silver_load=None,
        embeddings=EmbeddingRefreshSummary(
            requested_rows=0,
            embedded_rows=0,
            inserted_rows=0,
            updated_rows=0,
            database_rows=None,
            ingestion_run_id=None,
        ),
    )


class SequenceClock:
    def __init__(
        self,
        *values: datetime,
    ) -> None:
        self._values = iter(
            values
        )

    def __call__(self) -> datetime:
        return next(
            self._values
        )


def test_ingestion_accepts_zero_result_batch() -> None:
    client = Mock()
    writer = Mock()

    page = SimpleNamespace(
        page_number=1,
        result=SimpleNamespace(
            parsed=SimpleNamespace(
                total_notice_count=0,
                notices=[],
            )
        ),
    )

    client.iterate.return_value = [
        page
    ]

    writer.write_page.return_value = (
        SimpleNamespace(
            sha256="a" * 64
        )
    )

    artifact = zero_bronze()

    writer.finalize.return_value = (
        artifact
    )

    result = ingest_ted_window(
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
        client=client,
        writer=writer,
    )

    assert result.records_retrieved == 0
    assert result.total_source_matches == 0
    assert (
        result.unique_publication_numbers
        == 0
    )
    assert (
        result.run_artifact
        == artifact
    )

    writer.write_page.assert_called_once()

    finalize = (
        writer.finalize
        .call_args
        .kwargs
    )

    assert (
        finalize[
            "total_source_matches"
        ]
        == 0
    )
    assert (
        finalize["status"]
        == "completed"
    )


def test_core_zero_result_skips_downstream() -> None:
    ingestion = zero_ingestion()

    with (
        patch(
            "tendergraph.pipeline.refresh."
            "ingest_ted_window",
            return_value=ingestion,
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "build_silver_run_artifact",
        ) as build_silver,
        patch(
            "tendergraph.pipeline.refresh."
            "load_silver_tenders",
        ) as load_silver,
        patch(
            "tendergraph.pipeline.refresh."
            "reconcile_tender_embeddings",
        ) as refresh_embeddings,
    ):
        summary = (
            run_incremental_refresh(
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
                settings=Mock(),
            )
        )

    assert summary.no_data is True
    assert (
        summary.silver_artifact
        is None
    )
    assert (
        summary.silver_load
        is None
    )
    assert summary.changed_rows == 0
    assert (
        summary.embeddings
        .embedded_rows
        == 0
    )

    build_silver.assert_not_called()
    load_silver.assert_not_called()
    refresh_embeddings.assert_not_called()


def test_operational_zero_result_completes_audit(
    tmp_path: Path,
) -> None:
    refresh = zero_refresh()

    dbt = SimpleNamespace(
        success=True,
        command=(
            "dbt",
            "build",
        ),
        elapsed_seconds=0.25,
        result_type="RunExecutionResult",
    )

    clock = SequenceClock(
        datetime(
            2026,
            9,
            27,
            18,
            0,
            tzinfo=UTC,
        ),
        datetime(
            2026,
            9,
            27,
            18,
            1,
            tzinfo=UTC,
        ),
    )

    with (
        patch(
            "tendergraph.pipeline.operational."
            "run_incremental_refresh",
            return_value=refresh,
        ),
        patch(
            "tendergraph.pipeline.operational."
            "run_dbt_build",
            return_value=dbt,
        ),
    ):
        summary = run_operational_refresh(
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
            settings=Mock(),
            audit_root=tmp_path,
            clock=clock,
        )

    payload = json.loads(
        summary.audit_path.read_text()
    )

    assert payload["status"] == "completed"
    assert (
        payload["bronze_source_matches"]
        == 0
    )
    assert (
        payload["bronze_records_retrieved"]
        == 0
    )
    assert payload["silver_rows"] == 0
    assert payload["inserted_rows"] == 0
    assert payload["updated_rows"] == 0
    assert payload["unchanged_rows"] == 0
    assert (
        payload[
            "changed_publication_numbers"
        ]
        == []
    )
    assert (
        payload["embedding_embedded_rows"]
        == 0
    )
    assert payload["dbt_success"] is True
    assert (
        payload["failure_stage"]
        is None
    )


def test_cli_reports_zero_result_as_success(
    capsys,
) -> None:
    refresh = zero_refresh()

    summary = SimpleNamespace(
        refresh_id="refresh-zero",
        run_id="zero-run",
        refresh=refresh,
        dbt=SimpleNamespace(
            success=True
        ),
        audit_path=Path(
            "data/refresh/zero/"
            "refresh_audit.json"
        ),
    )

    with patch(
        "tendergraph.cli.refresh."
        "run_operational_refresh",
        return_value=summary,
    ):
        status = cli_main(
            [
                "--start-date",
                "2026-09-27",
                "--end-date",
                "2026-09-27",
                "--countries",
                "BEL",
            ]
        )

    output = (
        capsys
        .readouterr()
        .out
    )

    assert status == 0
    assert (
        "REFRESH COMPLETED (NO DATA)"
        in output
    )
    assert (
        "Bronze retrieved:  0"
        in output
    )
    assert (
        "Database rows:     unchanged"
        in output
    )
    assert (
        "dbt success:       True"
        in output
    )
