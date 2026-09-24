from datetime import date

import polars as pl
import pytest

from tendergraph.processing.quality import (
    validate_silver_tenders,
)


def make_frame(
    buyer_countries: list[list[str]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "publication_number": [
                f"{index}-2026"
                for index in range(
                    len(buyer_countries)
                )
            ],
            "publication_date": [
                date(2026, 9, 24)
                for _ in buyer_countries
            ],
            "title": [
                "Example tender"
                for _ in buyer_countries
            ],
            "buyer_countries": buyer_countries,
            "cpv_codes": [
                ["72000000"]
                for _ in buyer_countries
            ],
            "ingestion_run_id": [
                "run-123"
                for _ in buyer_countries
            ],
        }
    )


def test_quality_accepts_multicountry_notice() -> None:
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
