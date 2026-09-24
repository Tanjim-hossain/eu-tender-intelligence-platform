
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
            ],
            "notice-title": {
                "fra": "Marché exemple",
                "eng": "Example tender",
            },
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
        silver.buyer_name
        == "Example Authority"
    )

    assert (
        silver.buyer_name_language
        == "eng"
    )

    assert silver.buyer_countries == [
        "BEL"
    ]

    assert silver.cpv_codes == [
        "72000000",
        "72200000",
    ]

    assert (
        silver.first_cpv_code
        == "72000000"
    )

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
        silver.buyer_name
        == "Autorità Italiana"
    )

    assert (
        silver.buyer_name_language
        == "ita"
    )

    assert silver.first_cpv_code is None
