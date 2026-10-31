from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.decision.models import (
    BidNoBidDossier,
    DossierEvidenceSummary,
)
from tendergraph.product.models import ProductAccount

ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def _account() -> ProductAccount:
    return ProductAccount(
        id=ACCOUNT_ID,
        account_type="local",
        email=None,
        display_name=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _dossier() -> BidNoBidDossier:
    return BidNoBidDossier(
        account_id=ACCOUNT_ID,
        publication_number="123-2026",
        title="Example tender",
        buyer_name="Example Buyer",
        buyer_country="BEL",
        source_html_url="https://ted.europa.eu/example",
        pipeline_stage="reviewing",
        pipeline_note="",
        match_score=82,
        strategic_fit="strong",
        strategic_fit_reasons=["Strong stored fit."],
        deadline_readiness="open",
        days_to_deadline=21,
        notice_review_status="no_flags",
        notice_risk_level="low",
        document_package_status="ingested",
        document_coverage="substantive",
        checklist=[],
        risks=[],
        evidence_summary=DossierEvidenceSummary(
            requirement_count=0,
            hard_gate_count=0,
            hard_gates_verified=0,
            verified_count=0,
            needs_evidence_count=0,
            unreviewed_count=0,
        ),
        review_readiness="ready_for_bid_review",
        review_message="Proceed to human review.",
        reviewer_note="",
        next_actions=["Record the final human decision."],
        disclaimer="verify",
    )


def _client() -> tuple[TestClient, Mock]:
    app = create_app(use_lifespan=False)
    product_repository = Mock()
    product_repository.get_account.return_value = _account()
    app.state.product_repository = product_repository

    service = Mock()
    service.dossier.return_value = _dossier()
    service.update_review.return_value = _dossier()
    app.state.decision_dossier_service = service
    return TestClient(app), service


def test_get_decision_dossier_is_account_scoped() -> None:
    client, service = _client()

    response = client.get(
        f"/decisions/accounts/{ACCOUNT_ID}/opportunities/123-2026"
    )

    assert response.status_code == 200
    assert response.json()["review_readiness"] == "ready_for_bid_review"
    service.dossier.assert_called_once_with(
        ACCOUNT_ID,
        "123-2026",
    )


def test_put_decision_review_returns_refreshed_dossier() -> None:
    client, service = _client()

    response = client.put(
        (
            f"/decisions/accounts/{ACCOUNT_ID}/opportunities/"
            "123-2026/review"
        ),
        json={
            "items": [
                {
                    "key": "iso_27001",
                    "status": "verified",
                    "note": "Certificate checked.",
                }
            ],
            "reviewer_note": "Evidence reviewed.",
        },
    )

    assert response.status_code == 200
    call = service.update_review.call_args
    assert call.args[0] == ACCOUNT_ID
    assert call.args[1] == "123-2026"
    assert call.args[2].items[0].status == "verified"
    assert call.args[2].reviewer_note == "Evidence reviewed."


def test_blank_publication_number_is_rejected() -> None:
    client, _ = _client()

    response = client.get(
        f"/decisions/accounts/{ACCOUNT_ID}/opportunities/%20"
    )

    assert response.status_code == 422
