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


def test_operations_status_endpoint() -> None:
    from datetime import UTC, datetime
    from unittest.mock import patch

    from tendergraph.pipeline.status import (
        OperationalStatus,
    )

    application = create_app(
        use_lifespan=False
    )

    status = OperationalStatus(
        overall_status="ok",
        latest_refresh_id="refresh-1",
        latest_refresh_status="completed",
        latest_started_at_utc=datetime(
            2026,
            9,
            27,
            8,
            30,
            tzinfo=UTC,
        ),
        latest_finished_at_utc=datetime(
            2026,
            9,
            27,
            8,
            31,
            tzinfo=UTC,
        ),
        latest_window_end=date(
            2026,
            9,
            26,
        ),
        latest_dbt_success=True,
        last_successful_refresh_id=(
            "refresh-1"
        ),
        last_successful_finished_at_utc=(
            datetime(
                2026,
                9,
                27,
                8,
                31,
                tzinfo=UTC,
            )
        ),
        last_successful_window_end=date(
            2026,
            9,
            26,
        ),
        expected_data_through=date(
            2026,
            9,
            26,
        ),
        lag_days=0,
        stale=False,
        last_success_database_rows=5819,
        last_success_embedding_rows=5819,
        failure_stage=None,
        failure_type=None,
    )

    with patch(
        "tendergraph.api.app."
        "read_operational_status",
        return_value=status,
    ):
        client = TestClient(
            application
        )

        response = client.get(
            "/operations/status"
        )

    assert response.status_code == 200

    payload = response.json()

    assert (
        payload["overall_status"]
        == "ok"
    )
    assert payload["stale"] is False
    assert payload["lag_days"] == 0
    assert (
        payload[
            "last_success_database_rows"
        ]
        == 5819
    )
    assert (
        payload[
            "last_success_embedding_rows"
        ]
        == 5819
    )
    assert (
        "failure_message"
        not in payload
    )


def test_operations_status_unavailable_returns_503() -> None:
    from unittest.mock import patch

    application = create_app(
        use_lifespan=False
    )

    with patch(
        "tendergraph.api.app."
        "read_operational_status",
        side_effect=TypeError(
            "Malformed audit"
        ),
    ):
        client = TestClient(
            application
        )

        response = client.get(
            "/operations/status"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Operational status unavailable"
        )
    }
