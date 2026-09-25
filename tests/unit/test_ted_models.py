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
            "fra": (
                "Exemple de marché de "
                "plateforme de données"
            ),
        },
        "description-proc": {
            "eng": (
                "Procurement of a public-sector "
                "data platform."
            ),
        },
        "description-lot": {
            "eng": [
                "Lot 1: platform implementation",
                "Lot 2: support services",
            ],
        },
        "procedure-type": "open",
        "contract-nature": [
            "services",
            "services",
        ],
        "deadline": [
            "2026-10-20T12:00:00+02:00",
            "2026-10-25T12:00:00+02:00",
        ],
        "estimated-value-proc": "1250000.50",
        "estimated-value-cur-proc": "EUR",
        "place-of-performance-country-proc": [
            "BEL",
        ],
        "place-of-performance-subdiv-proc": [
            "BE242",
        ],
        "links": {
            "html": {
                "ENG": "https://example.com/tender",
            },
        },
    }


def test_ted_notice_parses_source_aliases() -> None:
    notice = TedNotice.model_validate(
        sample_notice()
    )

    assert (
        notice.publication_number
        == "123456-2026"
    )

    assert notice.buyer_country == ["BEL"]

    assert notice.classification_cpv == [
        "72000000",
        "72200000",
    ]

    assert notice.notice_title["eng"] == (
        "Example data platform tender"
    )

    assert notice.description_proc["eng"] == (
        "Procurement of a public-sector "
        "data platform."
    )

    assert notice.description_lot["eng"] == [
        "Lot 1: platform implementation",
        "Lot 2: support services",
    ]

    assert notice.procedure_type == "open"

    assert notice.contract_nature == [
        "services",
        "services",
    ]

    assert notice.deadline == [
        "2026-10-20T12:00:00+02:00",
        "2026-10-25T12:00:00+02:00",
    ]

    assert (
        notice.estimated_value_proc
        == "1250000.50"
    )

    assert (
        notice.estimated_value_cur_proc
        == "EUR"
    )

    assert (
        notice.place_of_performance_country_proc
        == ["BEL"]
    )

    assert (
        notice.place_of_performance_subdiv_proc
        == ["BE242"]
    )


def test_ted_notice_allows_missing_rich_fields() -> None:
    payload = sample_notice()

    rich_fields = [
        "description-proc",
        "description-lot",
        "procedure-type",
        "contract-nature",
        "deadline",
        "estimated-value-proc",
        "estimated-value-cur-proc",
        "place-of-performance-country-proc",
        "place-of-performance-subdiv-proc",
    ]

    for field in rich_fields:
        payload.pop(field)

    notice = TedNotice.model_validate(payload)

    assert notice.description_proc == {}
    assert notice.description_lot == {}
    assert notice.procedure_type is None
    assert notice.contract_nature == []
    assert notice.deadline == []
    assert notice.estimated_value_proc is None
    assert notice.estimated_value_cur_proc is None

    assert (
        notice.place_of_performance_country_proc
        == []
    )

    assert (
        notice.place_of_performance_subdiv_proc
        == []
    )


def test_search_response_parses_api_envelope() -> None:
    payload = {
        "notices": [sample_notice()],
        "totalNoticeCount": 1,
        "iterationNextToken": None,
        "timedOut": False,
    }

    response = TedSearchResponse.model_validate(
        payload
    )

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
    assert (
        payload["paginationMode"]
        == "PAGE_NUMBER"
    )
    assert payload["onlyLatestVersions"] is True


def test_iteration_request_uses_token_and_omits_page() -> None:
    request = TedSearchRequest(
        query="buyer-country = BEL",
        fields=["publication-number"],
        limit=250,
        pagination_mode="ITERATION",
        iteration_next_token="next-token-123",
    )

    payload = request.to_api_payload()

    assert payload["paginationMode"] == "ITERATION"

    assert (
        payload["iterationNextToken"]
        == "next-token-123"
    )

    assert "page" not in payload
    assert payload["limit"] == 250
