from __future__ import annotations

from datetime import UTC, datetime

from tendergraph.auth.repository import AuthRepository
from tendergraph.auth.security import (
    SESSION_TTL,
    create_session_token,
    hash_password,
    session_token_hash,
    verify_password,
)
from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.repository import ProductRepository
from tendergraph.product.schema import ensure_product_schema


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(settings, min_size=1, max_size=2)
    pool.open(wait=True)

    try:
        ensure_product_schema(pool)
        product = ProductRepository(pool)
        auth = AuthRepository(pool)

        local = product.create_local_account()
        profile = CompanyProfile(
            company_name="Auth Smoke Test",
            services=["Data engineering"],
            technologies=["Python"],
            target_countries=["BEL"],
        )
        product.upsert_profile(local.id, profile)

        password = "auth-smoke-password-123"
        registered = auth.register_account(
            email="auth-smoke@example.com",
            display_name="Auth Smoke",
            password_hash=hash_password(password),
            local_account_id=local.id,
        )
        assert registered.id == local.id
        assert registered.account_type == "registered"
        assert registered.email == "auth-smoke@example.com"

        login = auth.get_login_record("AUTH-SMOKE@example.com")
        assert login is not None
        assert login.account.id == local.id
        assert verify_password(password, login.password_hash)

        token = create_session_token()
        token_digest = session_token_hash(token)
        expires_at = datetime.now(UTC) + SESSION_TTL
        auth.create_session(
            account_id=registered.id,
            token_hash=token_digest,
            expires_at=expires_at,
        )
        session = auth.get_session(token_digest)
        assert session is not None
        assert session.account.id == registered.id

        state = product.get_state(registered.id)
        assert state is not None
        assert state.profile == profile

        auth.revoke_session(token_digest)
        assert auth.get_session(token_digest) is None

        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM product.accounts WHERE id = %(id)s",
                {"id": registered.id},
            )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
