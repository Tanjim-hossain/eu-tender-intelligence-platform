from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from tendergraph.alerts.models import AlertPreferences
from tendergraph.alerts.repository import AlertRepository
from tendergraph.api.app import create_app
from tendergraph.matching.models import CompanyMatchResult, CompanyProfile
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.product.models import ProductAccount, ProductState
from tendergraph.product.repository import ProductRepository

ACCOUNT_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _account(account_type: str = "local") -> ProductAccount:
    return ProductAccount(
        id=ACCOUNT_ID,
        account_type=account_type,
        email="alerts@example.com" if account_type == "registered" else None,
        display_name="Alerts User" if account_type == "registered" else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _profile() -> CompanyProfile:
    return CompanyProfile(
        company_name="Acme Data",
        services=["Data engineering"],
        target_countries=["BEL"],
    )


def _client(
    *,
    product_repository: Mock,
    alert_repository: Mock,
    matching_service: Mock | None = None,
) -> TestClient:
    application = create_app(use_lifespan=False)
    application.state.product_repository = product_repository
    application.state.alert_repository = alert_repository
    application.state.matching_service = matching_service or Mock(
        spec=CompanyMatchingService
    )
    return TestClient(application)


def test_get_default_alert_preferences() -> None:
    product_repository = Mock(spec=ProductRepository)
    product_repository.get_account.return_value = _account()
    alert_repository = Mock(spec=AlertRepository)
    alert_repository.get_preferences.return_value = AlertPreferences()

    response = _client(
        product_repository=product_repository,
        alert_repository=alert_repository,
    ).get(f"/alerts/accounts/{ACCOUNT_ID}/preferences")

    assert response.status_code == 200
    assert response.json()["min_match_score"] == 70.0
    assert response.json()["lookback_days"] == 14


def test_registered_alert_account_requires_session() -> None:
    product_repository = Mock(spec=ProductRepository)
    product_repository.get_account.return_value = _account("registered")
    alert_repository = Mock(spec=AlertRepository)

    response = _client(
        product_repository=product_repository,
        alert_repository=alert_repository,
    ).get(f"/alerts/accounts/{ACCOUNT_ID}/preferences")

    assert response.status_code == 401


def test_digest_requires_company_profile() -> None:
    product_repository = Mock(spec=ProductRepository)
    product_repository.get_account.return_value = _account()
    product_repository.get_state.return_value = ProductState(
        account=_account(),
        profile=None,
        opportunities=[],
    )
    alert_repository = Mock(spec=AlertRepository)

    response = _client(
        product_repository=product_repository,
        alert_repository=alert_repository,
    ).get(f"/alerts/accounts/{ACCOUNT_ID}/digest")

    assert response.status_code == 409
    assert "company profile" in response.json()["detail"].lower()


def test_refresh_returns_deduplicated_digest_summary() -> None:
    product_repository = Mock(spec=ProductRepository)
    product_repository.get_account.return_value = _account()
    product_repository.get_state.return_value = ProductState(
        account=_account(),
        profile=_profile(),
        opportunities=[],
    )
    alert_repository = Mock(spec=AlertRepository)
    alert_repository.get_preferences.return_value = AlertPreferences()
    alert_repository.insert_new_events.return_value = 0
    alert_repository.list_events.return_value = []
    alert_repository.event_counts.return_value = (0, 0)
    matching_service = Mock(spec=CompanyMatchingService)
    matching_service.match.return_value = CompanyMatchResult(
        profile_name="Acme Data",
        query="Data engineering",
        count=0,
        matches=[],
    )

    response = _client(
        product_repository=product_repository,
        alert_repository=alert_repository,
        matching_service=matching_service,
    ).post(f"/alerts/accounts/{ACCOUNT_ID}/refresh")

    assert response.status_code == 200
    assert response.json()["new_count"] == 0
    assert response.json()["digest"]["unread_count"] == 0
    alert_repository.touch_refresh.assert_called_once()
