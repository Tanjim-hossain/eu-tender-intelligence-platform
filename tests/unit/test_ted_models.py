from tendergraph.ingestion.models import (
    TedNotice,
    TedSearchRequest,
    TedSearchResponse,
)


def sample_notice() -> dict:
    return {
        "notice-type": "cn-standard",
        "publication-number": "123456-2026",
        "publication-date": "2026-09-24+02:00",
        "classification-cpv": [
            "72000000",
            "72200000",
        ],
        "buyer-name": {
            "eng": ["Example Public Authority"],
        },
        "buyer-country": ["BEL"],
        "notice-title": {
            "eng": "Example data platform tender",
            "fra": "Exemple de marché de plateforme de données",
        },
        "links": {
            "html": {
                "ENG": "https://example.com/tender",
            }
        },
    }


def test_ted_notice_parses_source_aliases() -> None:
    notice = TedNotice.model_validate(sample_notice())

    assert notice.publication_number == "123456-2026"
    assert notice.buyer_country == ["BEL"]
    assert notice.classification_cpv == [
        "72000000",
        "72200000",
    ]
    assert notice.notice_title["eng"] == (
        "Example data platform tender"
    )


def test_search_response_parses_api_envelope() -> None:
    payload = {
        "notices": [sample_notice()],
        "totalNoticeCount": 1,
        "iterationNextToken": None,
        "timedOut": False,
    }

    response = TedSearchResponse.model_validate(payload)

    assert response.total_notice_count == 1
    assert len(response.notices) == 1
    assert response.timed_out is False


def test_search_request_uses_ted_aliases() -> None:
    request = TedSearchRequest(
        query="buyer-country = BEL",
        fields=["publication-number"],
    )

    payload = request.to_api_payload()

    assert payload["checkQuerySyntax"] is False
    assert payload["paginationMode"] == "PAGE_NUMBER"
    assert payload["onlyLatestVersions"] is True
