from datetime import date
from unittest.mock import MagicMock, Mock

from fastapi.testclient import TestClient

from tendergraph.api.app import (
    create_app,
)
from tendergraph.api.models import (
    SearchRequest,
)
from tendergraph.search.service import (
    HybridSearchResult,
)


def test_search_request_normalizes_query() -> None:
    request = SearchRequest(
        query="  hospital   information system ",
    )

    assert (
        request.query
        == "hospital information system"
    )


def test_search_request_rejects_small_depth() -> None:
    try:
        SearchRequest(
            query="cloud platform",
            limit=20,
            retrieval_depth=10,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected validation error"
        )


def test_search_endpoint() -> None:
    application = create_app(
        use_lifespan=False
    )

    service = Mock()

    service.search.return_value = [
        HybridSearchResult(
            publication_number="648886-2026",
            publication_date=date(
                2026,
                9,
                18,
            ),
            title="Hospital information system",
            buyer_name="Example Buyer",
            buyer_country="DEU",
            procedure_type=None,
            estimated_value=None,
            estimated_value_currency=None,
            earliest_deadline=None,
            source_html_url=(
                "https://example.com/tender"
            ),
            rrf_score=0.020492,
            lexical_rank=None,
            semantic_rank=1,
            semantic_score=0.861415,
        )
    ]

    application.state.search_service = service

    client = TestClient(
        application
    )

    response = client.post(
        "/search",
        json={
            "query": (
                "hospital information system"
            ),
            "limit": 10,
            "retrieval_depth": 20,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["count"] == 1
    assert (
        payload["results"][0][
            "publication_number"
        ]
        == "648886-2026"
    )


def test_health_endpoint() -> None:
    application = create_app(
        use_lifespan=False
    )

    pool = MagicMock()

    connection = (
        pool.connection.return_value
        .__enter__.return_value
    )

    cursor = (
        connection.cursor.return_value
        .__enter__.return_value
    )

    cursor.fetchone.return_value = (1,)

    application.state.db_pool = pool

    client = TestClient(
        application
    )

    response = client.get(
        "/health"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
