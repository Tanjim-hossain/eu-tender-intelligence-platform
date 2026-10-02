from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.qualification.models import TenderQualification
from tendergraph.qualification.service import TenderNotFoundError


def qualification() -> TenderQualification:
    return TenderQualification(
        publication_number="123456-2026",
        publication_date=date(2026, 10, 1),
        title="Data platform services",
        buyer_name="Example Buyer",
        buyer_country="BEL",
        procedure_type="open",
        estimated_value=None,
        estimated_value_currency=None,
        earliest_deadline=None,
        source_html_url=(
            "https://ted.europa.eu/en/notice/-/detail/123456-2026"
        ),
        review_status="attention",
        risk_level="medium",
        evidence_coverage="limited",
        requirements=[],
        document_signals=[],
        risks=[],
        next_actions=[
            "Open the official TED notice and verify requirements."
        ],
        disclaimer="Evidence-grounded automated review.",
    )


def test_qualification_endpoint() -> None:
    application = create_app(
        use_lifespan=False
    )
    service = Mock()
    service.qualify.return_value = qualification()
    application.state.qualification_service = service

    response = TestClient(application).get(
        "/qualification/123456-2026"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["publication_number"] == "123456-2026"
    assert payload["risk_level"] == "medium"
    service.qualify.assert_called_once_with(
        "123456-2026"
    )


def test_qualification_endpoint_returns_404() -> None:
    application = create_app(
        use_lifespan=False
    )
    service = Mock()
    service.qualify.side_effect = TenderNotFoundError(
        "missing"
    )
    application.state.qualification_service = service

    response = TestClient(application).get(
        "/qualification/missing"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Tender not found"


def test_qualification_endpoint_requires_initialized_app() -> None:
    application = create_app(
        use_lifespan=False
    )

    response = TestClient(application).get(
        "/qualification/123456-2026"
    )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Application not initialized"
    )
