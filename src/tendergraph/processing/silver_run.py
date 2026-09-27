from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from tendergraph.processing.quality import (
    SilverQualitySummary,
    validate_silver_tenders,
)
from tendergraph.processing.silver import (
    build_silver_dataframe,
)

DEFAULT_SILVER_RUN_ROOT = Path(
    "data/silver/ted/runs"
)


@dataclass(frozen=True, slots=True)
class SilverRunArtifact:
    run_id: str
    source_run_dir: Path
    output_dir: Path
    parquet_path: Path
    row_count: int
    sha256: str
    quality: SilverQualitySummary


def _sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def build_silver_run_artifact(
    run_dir: Path,
    *,
    root: Path = DEFAULT_SILVER_RUN_ROOT,
) -> SilverRunArtifact:
    """Build and persist one validated Silver ingestion batch."""

    frame = build_silver_dataframe(
        run_dir
    )

    quality = validate_silver_tenders(
        frame
    )

    run_ids = (
        frame["ingestion_run_id"]
        .unique()
        .to_list()
    )

    if len(run_ids) != 1:
        raise RuntimeError(
            "Silver batch must contain exactly "
            "one ingestion run"
        )

    run_id = str(
        run_ids[0]
    )

    output_dir = (
        Path(root)
        / run_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    parquet_path = (
        output_dir
        / "tenders.parquet"
    )

    temporary_path = (
        output_dir
        / ".tenders.parquet.tmp"
    )

    temporary_path.unlink(
        missing_ok=True
    )

    try:
        frame.write_parquet(
            temporary_path,
            compression="zstd",
        )

        persisted = pl.read_parquet(
            temporary_path
        )

        persisted_quality = (
            validate_silver_tenders(
                persisted
            )
        )

        if (
            persisted.schema
            != frame.schema
        ):
            raise RuntimeError(
                "Persisted Silver schema does "
                "not match in-memory schema"
            )

        if (
            persisted_quality.row_count
            != quality.row_count
        ):
            raise RuntimeError(
                "Persisted Silver row count does "
                "not match in-memory batch"
            )

        persisted_run_ids = (
            persisted[
                "ingestion_run_id"
            ]
            .unique()
            .to_list()
        )

        if persisted_run_ids != [
            run_id
        ]:
            raise RuntimeError(
                "Persisted Silver ingestion run "
                "does not match source batch"
            )

        temporary_path.replace(
            parquet_path
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True
        )
        raise

    return SilverRunArtifact(
        run_id=run_id,
        source_run_dir=run_dir,
        output_dir=output_dir,
        parquet_path=parquet_path,
        row_count=quality.row_count,
        sha256=_sha256(
            parquet_path
        ),
        quality=quality,
    )
