from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import (
    OpportunitySnapshot,
    OpportunityStateUpdate,
    ProductAccount,
    ProductState,
    StoredOpportunityState,
)
from tendergraph.product.repository import ProductRepository

ACCOUNT_ID = UUID(
    "11111111-1111-4111-8111-111111111111"
)
NOW = datetime(
    2026,
    10,
    2,
    tzinfo=UTC,
)


def _account() -> ProductAccount:
    return ProductAccount(
        id=ACCOUNT_ID,
        account_type="local",
        email=None,
        display_name=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _profile() -> CompanyProfile:
    return CompanyProfile(
        company_name="Acme Data",
        services=[
            "Data engineering",
            "Analytics",
        ],
        technologies=["Python"],
        target_countries=["BEL"],
    )


def _snapshot() -> OpportunitySnapshot:
    return OpportunitySnapshot(
        title="Cloud data platform",
        buyer_name="Example Buyer",
        buyer_country="BEL",
        estimated_value=250000,
        estimated_value_currency="EUR",
        earliest_deadline=None,
        source_html_url=(
            "https://ted.europa.eu/en/notice/-/detail/1-2026"
        ),
    )


def _opportunity() -> StoredOpportunityState:
    return StoredOpportunityState(
        publication_number="1-2026",
        disposition="saved",
        pipeline_stage="reviewing",
        note="",
        match_score=91,
        snapshot=_snapshot(),
        created_at=NOW,
        updated_at=NOW,
    )


def _client(
    repository: Mock,
) -> TestClient:
    application = create_app(
        use_lifespan=False
    )
    application.state.product_repository = repository
    return TestClient(application)


def test_create_product_account() -> None:
    repository = Mock(
        spec=ProductRepository
    )
    repository.create_local_account.return_value = (
        _account()
    )

    response = _client(repository).post(
        "/product/accounts"
    )

    assert response.status_code == 201
    assert (
        response.json()["id"]
        == str(ACCOUNT_ID)
    )


def test_get_product_state() -> None:
    repository = Mock(
        spec=ProductRepository
    )
    repository.get_state.return_value = ProductState(
        account=_account(),
        profile=_profile(),
        opportunities=[_opportunity()],
    )

    response = _client(repository).get(
        f"/product/accounts/{ACCOUNT_ID}/state"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["company_name"] == "Acme Data"
    assert (
        payload["opportunities"][0]["pipeline_stage"]
        == "reviewing"
    )


def test_product_state_returns_404_for_unknown_account() -> None:
    repository = Mock(
        spec=ProductRepository
    )
    repository.get_state.return_value = None

    response = _client(repository).get(
        f"/product/accounts/{ACCOUNT_ID}/state"
    )

    assert response.status_code == 404


def test_put_profile() -> None:
    repository = Mock(
        spec=ProductRepository
    )
    repository.get_account.return_value = _account()
    repository.upsert_profile.return_value = _profile()

    response = _client(repository).put(
        f"/product/accounts/{ACCOUNT_ID}/profile",
        json=_profile().model_dump(
            mode="json"
        ),
    )

    assert response.status_code == 200
    assert (
        response.json()["company_name"]
        == "Acme Data"
    )


def test_put_saved_opportunity() -> None:
    repository = Mock(
        spec=ProductRepository
    )
    repository.get_account.return_value = _account()
    repository.upsert_opportunity.return_value = (
        _opportunity()
    )
    update = OpportunityStateUpdate(
        disposition="saved",
        match_score=91,
        snapshot=_snapshot(),
    )

    response = _client(repository).put(
        (
            f"/product/accounts/{ACCOUNT_ID}/"
            "opportunities/1-2026"
        ),
        json=update.model_dump(
            mode="json"
        ),
    )

    assert response.status_code == 200
    assert (
        response.json()["disposition"]
        == "saved"
    )
