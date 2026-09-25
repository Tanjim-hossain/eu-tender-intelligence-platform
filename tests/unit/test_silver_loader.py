from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tendergraph.database.silver_loader import (
    COPY_COLUMNS,
    _row_values,
)


def make_row() -> dict[str, object]:
    deadline = datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    )

    return {
        "publication_number": "123456-2026",
        "publication_date": date(
            2026,
            9,
            24,
        ),
        "publication_date_raw": (
            "2026-09-24+02:00"
        ),
        "notice_type": "cn-standard",
        "title": "Example tender",
        "title_language": "eng",
        "description": (
            "Example procurement description"
        ),
        "description_language": "eng",
        "lot_descriptions": [
            "Implementation",
            "Support",
        ],
        "lot_description_language": "eng",
        "lot_description_text": (
            "Implementation\nSupport"
        ),
        "buyer_name": "Example Authority",
        "buyer_name_language": "eng",
        "buyer_countries": [
            "BEL",
            "DEU",
        ],
        "first_buyer_country": "BEL",
        "cpv_codes": [
            "72000000",
            "72200000",
        ],
        "first_cpv_code": "72000000",
        "procedure_type": "open",
        "contract_natures": [
            "services",
        ],
        "deadlines": [
            deadline,
        ],
        "earliest_deadline": deadline,
        "latest_deadline": deadline,
        "estimated_value": Decimal(
            "129796146.856"
        ),
        "estimated_value_currency": "EUR",
        "performance_countries": [
            "BEL",
        ],
        "performance_regions": [
            "BE242",
        ],
        "source_html_url": (
            "https://example.com/tender"
        ),
        "source_xml_url": None,
        "ingestion_run_id": "run-123",
        "source": "TED Search API v3",
    }


def test_row_values_preserve_postgres_types() -> None:
    row = make_row()

    values = _row_values(row)

    mapped = dict(
        zip(
            COPY_COLUMNS,
            values,
            strict=True,
        )
    )

    assert mapped["publication_number"] == (
        "123456-2026"
    )

    assert mapped["publication_date"] == date(
        2026,
        9,
        24,
    )

    assert mapped["buyer_countries"] == [
        "BEL",
        "DEU",
    ]

    assert mapped["cpv_codes"] == [
        "72000000",
        "72200000",
    ]

    assert mapped["deadlines"] == [
        datetime(
            2026,
            10,
            20,
            10,
            tzinfo=UTC,
        )
    ]

    assert mapped["estimated_value"] == (
        Decimal("129796146.856")
    )

    assert mapped[
        "performance_countries"
    ] == ["BEL"]


def test_row_values_rejects_naive_deadline() -> None:
    row = make_row()

    aware_deadline = datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    )

    row["deadlines"] = [
        aware_deadline.replace(
            tzinfo=None
        )
    ]

    with pytest.raises(
        TypeError,
        match="timezone-aware",
    ):
        _row_values(row)


def test_row_values_rejects_float_value() -> None:
    row = make_row()

    row["estimated_value"] = 123.45

    with pytest.raises(
        TypeError,
        match="Decimal",
    ):
        _row_values(row)
