from __future__ import annotations

from dataclasses import dataclass

import polars as pl

TARGET_BUYER_COUNTRIES = [
    "BEL",
    "NLD",
    "DEU",
    "ITA",
]

UTC_DATETIME_DTYPE = pl.Datetime(
    time_unit="us",
    time_zone="UTC",
)

REQUIRED_COLUMNS = {
    "publication_number",
    "publication_date",
    "publication_date_raw",
    "notice_type",
    "title",
    "title_language",
    "description",
    "description_language",
    "lot_descriptions",
    "lot_description_language",
    "lot_description_text",
    "buyer_name",
    "buyer_name_language",
    "buyer_countries",
    "first_buyer_country",
    "cpv_codes",
    "first_cpv_code",
    "procedure_type",
    "contract_natures",
    "deadlines",
    "earliest_deadline",
    "latest_deadline",
    "estimated_value",
    "estimated_value_currency",
    "performance_countries",
    "performance_regions",
    "source_html_url",
    "source_xml_url",
    "ingestion_run_id",
    "source",
}


@dataclass(frozen=True, slots=True)
class SilverQualitySummary:
    row_count: int
    unique_publication_numbers: int
    duplicate_publication_numbers: int
    out_of_scope_rows: int
    rows_with_deadlines: int
    rows_with_estimated_value: int


def validate_silver_tenders(
    frame: pl.DataFrame,
) -> SilverQualitySummary:
    """Validate invariants of the enriched TED Silver dataset."""

    missing_columns = (
        REQUIRED_COLUMNS - set(frame.columns)
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
            "publication_date must have "
            "Polars Date dtype"
        )

    expected_deadline_list = pl.List(
        UTC_DATETIME_DTYPE
    )

    if (
        frame.schema["deadlines"]
        != expected_deadline_list
    ):
        raise ValueError(
            "deadlines must be a List of "
            "UTC Datetime values"
        )

    for column in [
        "earliest_deadline",
        "latest_deadline",
    ]:
        if (
            frame.schema[column]
            != UTC_DATETIME_DTYPE
        ):
            raise ValueError(
                f"{column} must have "
                "UTC Datetime dtype"
            )

    estimated_value_dtype = (
        frame.schema["estimated_value"]
    )

    if (
        estimated_value_dtype.base_type()
        != pl.Decimal
    ):
        raise ValueError(
            "estimated_value must have "
            "Polars Decimal dtype"
        )

    for column in [
        "buyer_countries",
        "cpv_codes",
        "lot_descriptions",
        "contract_natures",
        "performance_countries",
        "performance_regions",
    ]:
        if (
            frame.schema[column]
            != pl.List(pl.String)
        ):
            raise ValueError(
                f"{column} must have "
                "List(String) dtype"
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

    for column in [
        "publication_number",
        "publication_date",
        "title",
        "buyer_countries",
        "ingestion_run_id",
    ]:
        if frame[column].null_count():
            raise ValueError(
                f"{column} contains nulls"
            )

    if (
        frame["ingestion_run_id"].n_unique()
        != 1
    ):
        raise ValueError(
            "Silver dataset must contain "
            "exactly one ingestion_run_id"
        )

    empty_buyer_country_rows = frame.filter(
        pl.col("buyer_countries")
        .list.len()
        .fill_null(0)
        == 0
    ).height

    if empty_buyer_country_rows:
        raise ValueError(
            "buyer_countries contains "
            f"{empty_buyer_country_rows} "
            "empty lists"
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

    deadline_lengths = (
        pl.col("deadlines")
        .list.len()
        .fill_null(0)
    )

    invalid_deadline_presence = frame.filter(
        (
            (deadline_lengths == 0)
            & (
                pl.col(
                    "earliest_deadline"
                ).is_not_null()
                | pl.col(
                    "latest_deadline"
                ).is_not_null()
            )
        )
        | (
            (deadline_lengths > 0)
            & (
                pl.col(
                    "earliest_deadline"
                ).is_null()
                | pl.col(
                    "latest_deadline"
                ).is_null()
            )
        )
    ).height

    if invalid_deadline_presence:
        raise ValueError(
            "Deadline summary nullability "
            "does not match deadline lists"
        )

    invalid_deadline_bounds = frame.filter(
        (deadline_lengths > 0)
        & (
            (
                pl.col("earliest_deadline")
                != pl.col("deadlines").list.min()
            )
            | (
                pl.col("latest_deadline")
                != pl.col("deadlines").list.max()
            )
        )
    ).height

    if invalid_deadline_bounds:
        raise ValueError(
            "earliest_deadline/latest_deadline "
            "do not match deadline list bounds"
        )

    negative_value_rows = frame.filter(
        pl.col("estimated_value").is_not_null()
        & (
            pl.col("estimated_value")
            < 0
        )
    ).height

    if negative_value_rows:
        raise ValueError(
            "estimated_value contains "
            f"{negative_value_rows} "
            "negative values"
        )

    value_currency_mismatch = frame.filter(
        pl.col("estimated_value").is_null()
        != pl.col(
            "estimated_value_currency"
        ).is_null()
    ).height

    if value_currency_mismatch:
        raise ValueError(
            "estimated_value and currency "
            "nullability do not match"
        )

    rows_with_deadlines = frame.filter(
        deadline_lengths > 0
    ).height

    rows_with_estimated_value = frame.filter(
        pl.col("estimated_value").is_not_null()
    ).height

    return SilverQualitySummary(
        row_count=frame.height,
        unique_publication_numbers=unique_count,
        duplicate_publication_numbers=(
            duplicate_count
        ),
        out_of_scope_rows=out_of_scope_rows,
        rows_with_deadlines=(
            rows_with_deadlines
        ),
        rows_with_estimated_value=(
            rows_with_estimated_value
        ),
    )
