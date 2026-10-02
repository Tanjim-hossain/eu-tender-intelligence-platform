from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.auth.repository import AuthRepository, LoginRecord, SessionRecord
from tendergraph.product.models import ProductAccount

ACCOUNT_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _registered_account() -> ProductAccount:
    return ProductAccount(
        id=ACCOUNT_ID,
        account_type="registered",
        email="owner@example.com",
        display_name="Owner",
        created_at=NOW,
        updated_at=NOW,
    )


def _client(repository: Mock) -> TestClient:
    app = create_app(use_lifespan=False)
    app.state.auth_repository = repository
    return TestClient(app)


def test_register_sets_session_cookie() -> None:
    repository = Mock(spec=AuthRepository)
    repository.register_account.return_value = _registered_account()
    client = _client(repository)

    response = client.post(
        "/auth/register",
        json={
            "email": "Owner@Example.com",
            "password": "long-enough-password",
            "display_name": "Owner",
        },
    )

    assert response.status_code == 201
    assert response.json()["authenticated"] is True
    assert response.json()["account"]["email"] == "owner@example.com"
    assert "tendergraph_session=" in response.headers["set-cookie"]
    repository.create_session.assert_called_once()


def test_login_rejects_wrong_password() -> None:
    repository = Mock(spec=AuthRepository)
    repository.get_login_record.return_value = LoginRecord(
        account=_registered_account(),
        password_hash=(
            "scrypt$16384$8$1$invalid$invalid"
        ),
    )

    response = _client(repository).post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_returns_authenticated_session() -> None:
    repository = Mock(spec=AuthRepository)
    repository.get_session.return_value = SessionRecord(
        account=_registered_account(),
        expires_at=NOW + timedelta(days=1),
    )
    client = _client(repository)
    client.cookies.set("tendergraph_session", "opaque-token")

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["account"]["id"] == str(ACCOUNT_ID)


def test_me_without_cookie_is_anonymous() -> None:
    repository = Mock(spec=AuthRepository)

    response = _client(repository).get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "account": None,
        "expires_at": None,
    }
