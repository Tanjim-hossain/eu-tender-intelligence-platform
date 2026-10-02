from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.auth.repository import AuthRepository, SessionRecord
from tendergraph.product.models import ProductAccount, ProductState
from tendergraph.product.repository import ProductRepository

ACCOUNT_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_ACCOUNT_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _account(account_id: UUID = ACCOUNT_ID) -> ProductAccount:
    return ProductAccount(
        id=account_id,
        account_type="registered",
        email=f"{account_id}@example.com",
        display_name="Registered user",
        created_at=NOW,
        updated_at=NOW,
    )


def _client(product: Mock, auth: Mock) -> TestClient:
    app = create_app(use_lifespan=False)
    app.state.product_repository = product
    app.state.auth_repository = auth
    return TestClient(app)


def test_registered_product_state_requires_session() -> None:
    product = Mock(spec=ProductRepository)
    product.get_account.return_value = _account()
    auth = Mock(spec=AuthRepository)

    response = _client(product, auth).get(
        f"/product/accounts/{ACCOUNT_ID}/state"
    )

    assert response.status_code == 401
    product.get_state.assert_not_called()


def test_registered_session_cannot_read_another_account() -> None:
    product = Mock(spec=ProductRepository)
    product.get_account.return_value = _account(OTHER_ACCOUNT_ID)
    auth = Mock(spec=AuthRepository)
    auth.get_session.return_value = SessionRecord(
        account=_account(ACCOUNT_ID),
        expires_at=NOW + timedelta(days=1),
    )
    client = _client(product, auth)
    client.cookies.set("tendergraph_session", "opaque-token")

    response = client.get(
        f"/product/accounts/{OTHER_ACCOUNT_ID}/state"
    )

    assert response.status_code == 403
    product.get_state.assert_not_called()


def test_registered_session_reads_own_state() -> None:
    account = _account()
    product = Mock(spec=ProductRepository)
    product.get_account.return_value = account
    product.get_state.return_value = ProductState(
        account=account,
        profile=None,
        opportunities=[],
    )
    auth = Mock(spec=AuthRepository)
    auth.get_session.return_value = SessionRecord(
        account=account,
        expires_at=NOW + timedelta(days=1),
    )
    client = _client(product, auth)
    client.cookies.set("tendergraph_session", "opaque-token")

    response = client.get(
        f"/product/accounts/{ACCOUNT_ID}/state"
    )

    assert response.status_code == 200
    assert response.json()["account"]["id"] == str(ACCOUNT_ID)
