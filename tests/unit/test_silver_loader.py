from datetime import date

from tendergraph.database.silver_loader import (
    _row_values,
)


def test_row_values_preserve_postgres_types() -> None:
    row = {
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
        "source_html_url": (
            "https://example.com/tender"
        ),
        "source_xml_url": None,
        "ingestion_run_id": "run-123",
        "source": "TED Search API v3",
    }

    values = _row_values(row)

    assert values[0] == "123456-2026"
    assert values[1] == date(
        2026,
        9,
        24,
    )
    assert values[8] == [
        "BEL",
        "DEU",
    ]
    assert values[10] == [
        "72000000",
        "72200000",
    ]
