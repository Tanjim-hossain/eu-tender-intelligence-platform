from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.matching.models import (
    CompanyMatchResult,
    MatchSignals,
    TenderMatch,
)


def test_matches_endpoint_returns_personalized_results() -> None:
    application = create_app(use_lifespan=False)
    service = Mock()
    service.match.return_value = CompanyMatchResult(
        profile_name="Acme Data",
        query="data engineering Python Azure",
        count=1,
        matches=[
            TenderMatch(
                publication_number="123-2026",
                publication_date=date(2026, 10, 1),
                title="Cloud data platform",
                buyer_name="Example Buyer",
                buyer_country="BEL",
                procedure_type=None,
                estimated_value=Decimal(250000),
                estimated_value_currency="EUR",
                earliest_deadline=datetime(
                    2026,
                    10,
                    20,
                    12,
                    tzinfo=UTC,
                ),
                source_html_url="https://example.com/tender",
                match_score=91.2,
                signals=MatchSignals(
                    semantic_fit=0.88,
                    country_fit=1,
                    value_fit=1,
                    deadline_fit=1,
                    country_status="matched",
                    value_status="within_range",
                    deadline_status="open",
                    days_to_deadline=18,
                ),
                why_matches=[
                    "Strong semantic fit with the company capabilities"
                ],
                risks=[],
                rrf_score=0.03,
                lexical_rank=2,
                semantic_rank=1,
                semantic_score=0.88,
            )
        ],
    )
    application.state.matching_service = service
    client = TestClient(application)

    response = client.post(
        "/matches",
        json={
            "profile": {
                "company_name": "Acme Data",
                "services": ["data engineering"],
                "technologies": ["Python", "Azure"],
                "target_countries": ["BEL"],
                "preferred_min_value": "50000",
                "preferred_max_value": "500000",
            },
            "limit": 10,
            "retrieval_depth": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_name"] == "Acme Data"
    assert payload["count"] == 1
    assert payload["matches"][0]["match_score"] == 91.2
    assert payload["matches"][0]["signals"]["country_status"] == "matched"

    profile = service.match.call_args.args[0]
    assert profile.company_name == "Acme Data"
    assert profile.target_countries == ["BEL"]
    assert service.match.call_args.kwargs == {
        "limit": 10,
        "retrieval_depth": 50,
    }


def test_matches_endpoint_rejects_invalid_retrieval_depth() -> None:
    application = create_app(use_lifespan=False)
    application.state.matching_service = Mock()
    client = TestClient(application)

    response = client.post(
        "/matches",
        json={
            "profile": {
                "company_name": "Acme Data",
                "services": ["data engineering"],
            },
            "limit": 20,
            "retrieval_depth": 10,
        },
    )

    assert response.status_code == 422
