from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tendergraph.ingestion.models import TedNotice
from tendergraph.processing.silver import (
    normalize_notice,
)


def test_normalize_notice_prefers_english() -> None:
    notice = TedNotice.model_validate(
        {
            "notice-type": "cn-standard",
            "publication-number": "123456-2026",
            "publication-date": "2026-09-24+02:00",
            "classification-cpv": [
                "72000000",
                "72000000",
                "72200000",
            ],
            "buyer-name": {
                "fra": ["Autorité Exemple"],
                "eng": ["Example Authority"],
            },
            "buyer-country": [
                "BEL",
                "BEL",
                "NLD",
            ],
            "notice-title": {
                "fra": "Marché exemple",
                "eng": "Example tender",
            },
            "description-proc": {
                "fra": "Description française",
                "eng": "English description",
            },
            "description-lot": {
                "eng": [
                    "Cloud platform",
                    "Cloud platform",
                    "Support services",
                ],
                "fra": [
                    "Plateforme cloud",
                ],
            },
            "procedure-type": "open",
            "contract-nature": [
                "services",
                "services",
            ],
            "deadline": [
                "2026-10-25T12:00:00+02:00",
                "2026-10-20T10:00:00Z",
                "2026-10-20T12:00:00+02:00",
            ],
            "estimated-value-proc": "1250000.50",
            "estimated-value-cur-proc": "eur",
            "place-of-performance-country-proc": [
                "BEL",
                "BEL",
                "NLD",
            ],
            "place-of-performance-subdiv-proc": [
                "BE242",
                "BE242",
            ],
            "links": {
                "html": {
                    "FRA": "https://example.com/fr",
                    "ENG": "https://example.com/en",
                },
                "xml": {
                    "MUL": "https://example.com/xml",
                },
            },
        }
    )

    silver = normalize_notice(
        notice,
        run_id="run-123",
    )

    assert silver.title == "Example tender"
    assert silver.title_language == "eng"

    assert (
        silver.description
        == "English description"
    )
    assert silver.description_language == "eng"

    assert silver.lot_descriptions == [
        "Cloud platform",
        "Support services",
    ]
    assert (
        silver.lot_description_language
        == "eng"
    )
    assert silver.lot_description_text == (
        "Cloud platform\nSupport services"
    )

    assert (
        silver.buyer_name
        == "Example Authority"
    )
    assert (
        silver.buyer_name_language
        == "eng"
    )

    assert silver.buyer_countries == [
        "BEL",
        "NLD",
    ]

    assert silver.cpv_codes == [
        "72000000",
        "72200000",
    ]

    assert (
        silver.first_cpv_code
        == "72000000"
    )

    assert silver.procedure_type == "open"

    assert silver.contract_natures == [
        "services",
    ]

    assert silver.deadlines == [
        datetime(
            2026,
            10,
            20,
            10,
            tzinfo=UTC,
        ),
        datetime(
            2026,
            10,
            25,
            10,
            tzinfo=UTC,
        ),
    ]

    assert silver.earliest_deadline == datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    )

    assert silver.latest_deadline == datetime(
        2026,
        10,
        25,
        10,
        tzinfo=UTC,
    )

    assert silver.estimated_value == Decimal(
        "1250000.50"
    )

    assert (
        silver.estimated_value_currency
        == "EUR"
    )

    assert silver.performance_countries == [
        "BEL",
        "NLD",
    ]

    assert silver.performance_regions == [
        "BE242",
    ]

    assert (
        silver.publication_date.isoformat()
        == "2026-09-24"
    )

    assert (
        silver.source_html_url
        == "https://example.com/en"
    )


def test_normalize_notice_has_language_fallback() -> None:
    notice = TedNotice.model_validate(
        {
            "notice-type": "cn-standard",
            "publication-number": "654321-2026",
            "publication-date": "2026-09-24+02:00",
            "classification-cpv": [],
            "buyer-name": {
                "ita": ["Autorità Italiana"],
            },
            "buyer-country": ["ITA"],
            "notice-title": {
                "ita": "Gara esempio",
            },
            "description-proc": {
                "ita": "Descrizione esempio",
            },
            "description-lot": {
                "ita": [
                    "Lotto unico",
                ],
            },
            "links": {},
        }
    )

    silver = normalize_notice(
        notice,
        run_id="run-456",
    )

    assert silver.title == "Gara esempio"
    assert silver.title_language == "ita"

    assert (
        silver.description
        == "Descrizione esempio"
    )
    assert (
        silver.description_language
        == "ita"
    )

    assert silver.lot_descriptions == [
        "Lotto unico",
    ]

    assert (
        silver.lot_description_language
        == "ita"
    )

    assert (
        silver.buyer_name
        == "Autorità Italiana"
    )

    assert (
        silver.buyer_name_language
        == "ita"
    )

    assert silver.first_cpv_code is None

    assert silver.procedure_type is None
    assert silver.contract_natures == []
    assert silver.deadlines == []
    assert silver.earliest_deadline is None
    assert silver.latest_deadline is None
    assert silver.estimated_value is None
    assert (
        silver.estimated_value_currency
        is None
    )
    assert silver.performance_countries == []
    assert silver.performance_regions == []


def test_normalize_notice_rejects_naive_deadline() -> None:
    notice = TedNotice.model_validate(
        {
            "notice-type": "cn-standard",
            "publication-number": "111111-2026",
            "publication-date": "2026-09-24+02:00",
            "buyer-country": ["BEL"],
            "notice-title": {
                "eng": "Example tender",
            },
            "deadline": [
                "2026-10-20T12:00:00",
            ],
        }
    )

    with pytest.raises(
        ValueError,
        match="timezone offset",
    ):
        normalize_notice(
            notice,
            run_id="run-789",
        )


def test_normalize_notice_rejects_invalid_value() -> None:
    notice = TedNotice.model_validate(
        {
            "notice-type": "cn-standard",
            "publication-number": "222222-2026",
            "publication-date": "2026-09-24+02:00",
            "buyer-country": ["BEL"],
            "notice-title": {
                "eng": "Example tender",
            },
            "estimated-value-proc": "not-a-number",
        }
    )

    with pytest.raises(
        ValueError,
        match="estimated value",
    ):
        normalize_notice(
            notice,
            run_id="run-999",
        )
