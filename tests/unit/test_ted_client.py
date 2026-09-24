import httpx
import pytest

from tendergraph.ingestion.client import (
    TedApiError,
    TedClient,
)
from tendergraph.ingestion.models import TedSearchRequest


def sample_response() -> dict:
    return {
        "notices": [
            {
                "notice-type": "cn-standard",
                "publication-number": "123456-2026",
                "publication-date": "2026-09-24+02:00",
                "classification-cpv": ["72000000"],
                "buyer-name": {
                    "eng": ["Example Authority"],
                },
                "buyer-country": ["BEL"],
                "notice-title": {
                    "eng": "Example tender",
                },
                "links": {},
            }
        ],
        "totalNoticeCount": 1,
        "iterationNextToken": None,
        "timedOut": False,
    }


def search_request() -> TedSearchRequest:
    return TedSearchRequest(
        query="buyer-country = BEL",
        fields=[
            "publication-number",
            "publication-date",
        ],
    )


def test_client_parses_successful_response() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=sample_response(),
        )

    client = TedClient(
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    result = client.search(search_request())

    assert result.raw["totalNoticeCount"] == 1
    assert result.parsed.total_notice_count == 1
    assert (
        result.parsed.notices[0].publication_number
        == "123456-2026"
    )


def test_client_retries_retryable_status() -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return httpx.Response(
                503,
                json={"detail": "temporary failure"},
            )

        return httpx.Response(
            200,
            json=sample_response(),
        )

    client = TedClient(
        transport=httpx.MockTransport(handler),
        max_retries=1,
        backoff_seconds=0,
    )

    result = client.search(search_request())

    assert attempts == 2
    assert result.parsed.total_notice_count == 1


def test_client_raises_on_non_retryable_error() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            400,
            json={"detail": "bad query"},
        )

    client = TedClient(
        transport=httpx.MockTransport(handler),
        max_retries=3,
        backoff_seconds=0,
    )

    with pytest.raises(TedApiError):
        client.search(search_request())


def test_client_iterates_using_next_token() -> None:
    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            payload = sample_response()
            payload["totalNoticeCount"] = 2
            payload["iterationNextToken"] = (
                "token-page-2"
            )

            return httpx.Response(
                200,
                json=payload,
            )

        payload = sample_response()
        payload["totalNoticeCount"] = 2

        # Deliberately keep a token even though
        # totalNoticeCount has now been reached.
        # The iterator must stop by record count.
        payload["iterationNextToken"] = (
            "token-after-logical-end"
        )

        return httpx.Response(
            200,
            json=payload,
        )

    client = TedClient(
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    request = TedSearchRequest(
        query="buyer-country = BEL",
        fields=["publication-number"],
        limit=250,
    )

    pages = list(
        client.iterate(request)
    )

    assert len(pages) == 2
    assert call_count == 2

    assert pages[0].page_number == 1
    assert (
        pages[0].request.iteration_next_token
        is None
    )

    assert pages[1].page_number == 2
    assert (
        pages[1].request.iteration_next_token
        == "token-page-2"
    )
