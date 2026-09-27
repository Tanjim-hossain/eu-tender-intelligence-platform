from pathlib import Path
from unittest.mock import patch

import polars as pl

from tendergraph.processing.quality import (
    SilverQualitySummary,
)
from tendergraph.processing.silver_run import (
    build_silver_run_artifact,
)


def quality() -> SilverQualitySummary:
    return SilverQualitySummary(
        row_count=2,
        unique_publication_numbers=2,
        duplicate_publication_numbers=0,
        out_of_scope_rows=0,
        rows_with_deadlines=0,
        rows_with_estimated_value=0,
    )


def frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "publication_number": [
                "A",
                "B",
            ],
            "ingestion_run_id": [
                "run-1",
                "run-1",
            ],
        }
    )


def test_build_silver_run_artifact(
    tmp_path: Path,
) -> None:
    silver_frame = frame()

    with (
        patch(
            "tendergraph.processing."
            "silver_run."
            "build_silver_dataframe",
            return_value=silver_frame,
        ),
        patch(
            "tendergraph.processing."
            "silver_run."
            "validate_silver_tenders",
            return_value=quality(),
        ),
    ):
        artifact = (
            build_silver_run_artifact(
                Path(
                    "bronze/run-1"
                ),
                root=tmp_path,
            )
        )

    assert artifact.run_id == "run-1"

    assert artifact.parquet_path == (
        tmp_path
        / "run-1"
        / "tenders.parquet"
    )

    assert artifact.parquet_path.exists()

    assert artifact.row_count == 2

    assert len(
        artifact.sha256
    ) == 64

    persisted = pl.read_parquet(
        artifact.parquet_path
    )

    assert persisted.equals(
        silver_frame
    )


def test_silver_run_write_is_idempotent(
    tmp_path: Path,
) -> None:
    silver_frame = frame()

    with (
        patch(
            "tendergraph.processing."
            "silver_run."
            "build_silver_dataframe",
            return_value=silver_frame,
        ),
        patch(
            "tendergraph.processing."
            "silver_run."
            "validate_silver_tenders",
            return_value=quality(),
        ),
    ):
        first = (
            build_silver_run_artifact(
                Path(
                    "bronze/run-1"
                ),
                root=tmp_path,
            )
        )

        second = (
            build_silver_run_artifact(
                Path(
                    "bronze/run-1"
                ),
                root=tmp_path,
            )
        )

    assert (
        first.parquet_path
        == second.parquet_path
    )

    assert (
        first.sha256
        == second.sha256
    )

    assert not (
        tmp_path
        / "run-1"
        / ".tenders.parquet.tmp"
    ).exists()
