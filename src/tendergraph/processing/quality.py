from __future__ import annotations

from dataclasses import dataclass

import polars as pl

TARGET_BUYER_COUNTRIES = [
    "BEL",
    "NLD",
    "DEU",
    "ITA",
]


@dataclass(frozen=True, slots=True)
class SilverQualitySummary:
    row_count: int
    unique_publication_numbers: int
    duplicate_publication_numbers: int
    out_of_scope_rows: int


def validate_silver_tenders(
    frame: pl.DataFrame,
) -> SilverQualitySummary:
    """Validate core invariants of the TED Silver dataset."""

    required_columns = {
        "publication_number",
        "publication_date",
        "title",
        "buyer_countries",
        "cpv_codes",
        "ingestion_run_id",
    }

    missing_columns = (
        required_columns - set(frame.columns)
    )

    if missing_columns:
        raise ValueError(
            "Silver dataset is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if frame.height == 0:
        raise ValueError(
            "Silver dataset must not be empty"
        )

    if frame.schema["publication_date"] != pl.Date:
        raise ValueError(
            "publication_date must have Polars Date dtype"
        )

    unique_count = (
        frame["publication_number"].n_unique()
    )

    duplicate_count = (
        frame.height - unique_count
    )

    if duplicate_count:
        raise ValueError(
            "Duplicate publication numbers found: "
            f"{duplicate_count}"
        )

    if frame["publication_number"].null_count():
        raise ValueError(
            "publication_number contains nulls"
        )

    if frame["publication_date"].null_count():
        raise ValueError(
            "publication_date contains nulls"
        )

    if frame["title"].null_count():
        raise ValueError(
            "title contains nulls"
        )

    scoped = frame.with_columns(
        pl.col("buyer_countries")
        .list.eval(
            pl.element().is_in(
                TARGET_BUYER_COUNTRIES
            )
        )
        .list.any()
        .alias("_has_target_country")
    )

    out_of_scope_rows = scoped.filter(
        ~pl.col("_has_target_country")
    ).height

    if out_of_scope_rows:
        raise ValueError(
            "Silver dataset contains "
            f"{out_of_scope_rows} notices "
            "without a target buyer country"
        )

    return SilverQualitySummary(
        row_count=frame.height,
        unique_publication_numbers=unique_count,
        duplicate_publication_numbers=(
            duplicate_count
        ),
        out_of_scope_rows=out_of_scope_rows,
    )
