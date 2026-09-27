from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.database.silver_loader import (
    LoadSummary,
)
from tendergraph.ingestion.runner import (
    TedIngestionResult,
)
from tendergraph.pipeline.refresh import (
    run_incremental_refresh,
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


def test_refresh_connects_changed_ids_to_embeddings() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    load_summary = silver_load(
        inserted=("A",),
        updated=("B",),
    )

    embedding_summary = (
        EmbeddingRefreshSummary(
            requested_rows=2,
            embedded_rows=2,
            inserted_rows=1,
            updated_rows=1,
            database_rows=4885,
            ingestion_run_id="run-1",
        )
    )

    with (
        patch(
            "tendergraph.pipeline.refresh."
            "ingest_ted_window",
            return_value=ingestion(),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "build_silver_run_artifact",
            return_value=(
                silver_artifact()
            ),
        ) as build_silver,
        patch(
            "tendergraph.pipeline.refresh."
            "load_silver_tenders",
            return_value=load_summary,
        ) as load_silver,
        patch(
            "tendergraph.pipeline.refresh."
            "refresh_tender_embeddings",
            return_value=(
                embedding_summary
            ),
        ) as refresh_embeddings,
    ):
        summary = (
            run_incremental_refresh(
                start_date=date(
                    2026,
                    9,
                    25,
                ),
                end_date=date(
                    2026,
                    9,
                    25,
                ),
                countries=[
                    "BEL",
                    "NLD",
                ],
                settings=settings,
                silver_root=Path(
                    "silver"
                ),
            )
        )

    build_silver.assert_called_once_with(
        Path(
            "bronze/run-1"
        ),
        root=Path(
            "silver"
        ),
    )

    load_silver.assert_called_once_with(
        Path(
            "silver/run-1/"
            "tenders.parquet"
        ),
        settings,
    )

    refresh_embeddings.assert_called_once_with(
        settings,
        (
            "A",
            "B",
        ),
        batch_size=32,
        encoder=None,
    )

    assert summary.run_id == "run-1"

    assert (
        summary.changed_publication_numbers
        == (
            "A",
            "B",
        )
    )

    assert summary.changed_rows == 2

    assert (
        summary.embeddings
        == embedding_summary
    )


def test_refresh_skips_embedding_model_when_no_changes() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    with (
        patch(
            "tendergraph.pipeline.refresh."
            "ingest_ted_window",
            return_value=ingestion(),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "build_silver_run_artifact",
            return_value=(
                silver_artifact()
            ),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "load_silver_tenders",
            return_value=(
                silver_load()
            ),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "refresh_tender_embeddings"
        ) as refresh_embeddings,
    ):
        summary = (
            run_incremental_refresh(
                start_date=date(
                    2026,
                    9,
                    25,
                ),
                end_date=date(
                    2026,
                    9,
                    25,
                ),
                countries=["BEL"],
                settings=settings,
            )
        )

    refresh_embeddings.assert_not_called()

    assert summary.changed_rows == 0
    assert (
        summary.embeddings.requested_rows
        == 0
    )
    assert (
        summary.embeddings.database_rows
        is None
    )


def test_refresh_rejects_run_id_mismatch() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    with (
        patch(
            "tendergraph.pipeline.refresh."
            "ingest_ted_window",
            return_value=ingestion(
                "run-1"
            ),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "build_silver_run_artifact",
            return_value=(
                silver_artifact(
                    "run-2"
                )
            ),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "load_silver_tenders"
        ) as load_silver,
    ):
        try:
            run_incremental_refresh(
                start_date=date(
                    2026,
                    9,
                    25,
                ),
                end_date=date(
                    2026,
                    9,
                    25,
                ),
                countries=["BEL"],
                settings=settings,
            )
        except RuntimeError as exc:
            assert (
                "run IDs do not match"
                in str(exc)
            )
        else:
            raise AssertionError(
                "Expected run ID mismatch"
            )

    load_silver.assert_not_called()


def test_refresh_reports_stage_order() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    stages: list[str] = []

    with (
        patch(
            "tendergraph.pipeline.refresh."
            "ingest_ted_window",
            return_value=ingestion(),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "build_silver_run_artifact",
            return_value=(
                silver_artifact()
            ),
        ),
        patch(
            "tendergraph.pipeline.refresh."
            "load_silver_tenders",
            return_value=(
                silver_load()
            ),
        ),
    ):
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
            settings=settings,
            on_stage_start=stages.append,
        )

    assert stages == [
        "ingestion",
        "silver_build",
        "silver_load",
        "embeddings",
    ]
