from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from tendergraph.processing.quality import (
    validate_silver_tenders,
)

UTC_DTYPE = pl.Datetime(
    time_unit="us",
    time_zone="UTC",
)


def make_frame(
    buyer_countries: list[list[str]],
) -> pl.DataFrame:
    row_count = len(buyer_countries)

    deadline = datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    )

    frame = pl.DataFrame(
        {
            "publication_number": [
                f"{index}-2026"
                for index in range(row_count)
            ],
            "publication_date": [
                date(2026, 9, 24)
                for _ in range(row_count)
            ],
            "publication_date_raw": [
                "2026-09-24+02:00"
                for _ in range(row_count)
            ],
            "notice_type": [
                "cn-standard"
                for _ in range(row_count)
            ],
            "title": [
                "Example tender"
                for _ in range(row_count)
            ],
            "title_language": [
                "eng"
                for _ in range(row_count)
            ],
            "description": [
                "Example description"
                for _ in range(row_count)
            ],
            "description_language": [
                "eng"
                for _ in range(row_count)
            ],
            "lot_descriptions": [
                ["Example lot"]
                for _ in range(row_count)
            ],
            "lot_description_language": [
                "eng"
                for _ in range(row_count)
            ],
            "lot_description_text": [
                "Example lot"
                for _ in range(row_count)
            ],
            "buyer_name": [
                "Example Authority"
                for _ in range(row_count)
            ],
            "buyer_name_language": [
                "eng"
                for _ in range(row_count)
            ],
            "buyer_countries": buyer_countries,
            "first_buyer_country": [
                countries[0]
                for countries in buyer_countries
            ],
            "cpv_codes": [
                ["72000000"]
                for _ in range(row_count)
            ],
            "first_cpv_code": [
                "72000000"
                for _ in range(row_count)
            ],
            "procedure_type": [
                "open"
                for _ in range(row_count)
            ],
            "contract_natures": [
                ["services"]
                for _ in range(row_count)
            ],
            "deadlines": [
                [deadline]
                for _ in range(row_count)
            ],
            "earliest_deadline": [
                deadline
                for _ in range(row_count)
            ],
            "latest_deadline": [
                deadline
                for _ in range(row_count)
            ],
            "estimated_value": [
                Decimal("100.00000000")
                for _ in range(row_count)
            ],
            "estimated_value_currency": [
                "EUR"
                for _ in range(row_count)
            ],
            "performance_countries": [
                ["BEL"]
                for _ in range(row_count)
            ],
            "performance_regions": [
                ["BE242"]
                for _ in range(row_count)
            ],
            "source_html_url": [
                "https://example.com"
                for _ in range(row_count)
            ],
            "source_xml_url": [
                "https://example.com/xml"
                for _ in range(row_count)
            ],
            "ingestion_run_id": [
                "run-123"
                for _ in range(row_count)
            ],
            "source": [
                "TED Search API v3"
                for _ in range(row_count)
            ],
        },
        schema_overrides={
            "deadlines": pl.List(UTC_DTYPE),
            "earliest_deadline": UTC_DTYPE,
            "latest_deadline": UTC_DTYPE,
            "estimated_value": pl.Decimal(
                precision=38,
                scale=8,
            ),
        },
    )

    return frame


def test_quality_accepts_enriched_dataset() -> None:
    frame = make_frame(
        [
            ["DNK", "DEU"],
            ["BEL"],
        ]
    )

    summary = validate_silver_tenders(
        frame
    )

    assert summary.row_count == 2
    assert summary.out_of_scope_rows == 0
    assert summary.rows_with_deadlines == 2
    assert (
        summary.rows_with_estimated_value
        == 2
    )


def test_quality_rejects_out_of_scope_notice() -> None:
    frame = make_frame(
        [
            ["DNK"],
        ]
    )

    with pytest.raises(
        ValueError,
        match="without a target buyer country",
    ):
        validate_silver_tenders(frame)


def test_quality_rejects_negative_value() -> None:
    frame = make_frame(
        [
            ["BEL"],
        ]
    ).with_columns(
        pl.lit(
            Decimal("-1.00000000"),
            dtype=pl.Decimal(
                precision=38,
                scale=8,
            ),
        ).alias("estimated_value")
    )

    with pytest.raises(
        ValueError,
        match="negative values",
    ):
        validate_silver_tenders(frame)


def test_quality_rejects_deadline_bound_mismatch() -> None:
    frame = make_frame(
        [
            ["BEL"],
        ]
    )

    wrong_deadline = datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    ) + timedelta(hours=1)

    frame = frame.with_columns(
        pl.lit(
            wrong_deadline,
            dtype=UTC_DTYPE,
        ).alias("earliest_deadline")
    )

    with pytest.raises(
        ValueError,
        match="deadline list bounds",
    ):
        validate_silver_tenders(frame)


def test_quality_rejects_value_currency_mismatch() -> None:
    frame = make_frame(
        [
            ["BEL"],
        ]
    ).with_columns(
        pl.lit(
            None,
            dtype=pl.String,
        ).alias(
            "estimated_value_currency"
        )
    )

    with pytest.raises(
        ValueError,
        match="currency nullability",
    ):
        validate_silver_tenders(frame)


def test_quality_requires_enriched_schema() -> None:
    frame = make_frame(
        [
            ["BEL"],
        ]
    ).drop("description")

    with pytest.raises(
        ValueError,
        match="missing columns",
    ):
        validate_silver_tenders(frame)
