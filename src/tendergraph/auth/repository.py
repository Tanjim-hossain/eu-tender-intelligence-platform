from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool

from tendergraph.product.models import ProductAccount


class EmailAlreadyRegisteredError(RuntimeError):
    """Raised when registration attempts to reuse an email address."""


class LocalAccountClaimError(RuntimeError):
    """Raised when a local account cannot be upgraded in place."""


@dataclass(frozen=True, slots=True)
class LoginRecord:
    account: ProductAccount
    password_hash: str


@dataclass(frozen=True, slots=True)
class SessionRecord:
    account: ProductAccount
    expires_at: datetime


def _account_from_row(row: tuple[Any, ...]) -> ProductAccount:
    return ProductAccount(
        id=row[0],
        account_type=row[1],
        email=row[2],
        display_name=row[3],
        created_at=row[4],
        updated_at=row[5],
    )


class AuthRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def register_account(
        self,
        *,
        email: str,
        display_name: str | None,
        password_hash: str,
        local_account_id: UUID | None = None,
    ) -> ProductAccount:
        try:
            with (
                self._pool.connection() as connection,
                connection.cursor() as cursor,
            ):
                if local_account_id is not None:
                    cursor.execute(
                        """
                        SELECT account_type
                        FROM product.accounts
                        WHERE id = %(account_id)s
                        FOR UPDATE;
                        """,
                        {"account_id": local_account_id},
                    )
                    row = cursor.fetchone()
                    if row is None or row[0] != "local":
                        raise LocalAccountClaimError(
                            "Local account is unavailable for registration"
                        )
                    cursor.execute(
                        """
                        UPDATE product.accounts
                        SET account_type = 'registered',
                            email = %(email)s,
                            display_name = %(display_name)s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %(account_id)s
                        RETURNING
                            id, account_type, email, display_name,
                            created_at, updated_at;
                        """,
                        {
                            "account_id": local_account_id,
                            "email": email,
                            "display_name": display_name,
                        },
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO product.accounts (
                            id, account_type, email, display_name
                        )
                        VALUES (
                            %(id)s, 'registered', %(email)s, %(display_name)s
                        )
                        RETURNING
                            id, account_type, email, display_name,
                            created_at, updated_at;
                        """,
                        {
                            "id": uuid4(),
                            "email": email,
                            "display_name": display_name,
                        },
                    )

                account_row = cursor.fetchone()
                if account_row is None:
                    raise RuntimeError("Registration returned no account")
                account = _account_from_row(account_row)
                cursor.execute(
                    """
                    INSERT INTO product.password_credentials (
                        account_id, password_hash
                    )
                    VALUES (%(account_id)s, %(password_hash)s);
                    """,
                    {
                        "account_id": account.id,
                        "password_hash": password_hash,
                    },
                )
                return account
        except UniqueViolation as exc:
            raise EmailAlreadyRegisteredError(
                "Email address is already registered"
            ) from exc

    def get_login_record(self, email: str) -> LoginRecord | None:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                SELECT
                    a.id, a.account_type, a.email, a.display_name,
                    a.created_at, a.updated_at,
                    c.password_hash
                FROM product.accounts AS a
                JOIN product.password_credentials AS c
                    ON c.account_id = a.id
                WHERE a.account_type = 'registered'
                  AND lower(a.email) = lower(%(email)s);
                """,
                {"email": email},
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return LoginRecord(
            account=_account_from_row(row[:6]),
            password_hash=row[6],
        )

    def create_session(
        self,
        *,
        account_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO product.auth_sessions (
                    id, account_id, token_hash, expires_at
                )
                VALUES (
                    %(id)s, %(account_id)s, %(token_hash)s, %(expires_at)s
                );
                """,
                {
                    "id": uuid4(),
                    "account_id": account_id,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                },
            )

    def get_session(self, token_hash: str) -> SessionRecord | None:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                SELECT
                    a.id, a.account_type, a.email, a.display_name,
                    a.created_at, a.updated_at,
                    s.expires_at
                FROM product.auth_sessions AS s
                JOIN product.accounts AS a
                    ON a.id = s.account_id
                WHERE s.token_hash = %(token_hash)s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > CURRENT_TIMESTAMP
                  AND a.account_type = 'registered';
                """,
                {"token_hash": token_hash},
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                UPDATE product.auth_sessions
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE token_hash = %(token_hash)s;
                """,
                {"token_hash": token_hash},
            )
        return SessionRecord(
            account=_account_from_row(row[:6]),
            expires_at=row[6],
        )

    def revoke_session(self, token_hash: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE product.auth_sessions
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE token_hash = %(token_hash)s
                  AND revoked_at IS NULL;
                """,
                {"token_hash": token_hash},
            )

    def purge_stale_sessions(self) -> int:
        with self._pool.connection() as connection:
            result = connection.execute(
                """
                DELETE FROM product.auth_sessions
                WHERE expires_at <= CURRENT_TIMESTAMP
                   OR revoked_at IS NOT NULL;
                """
            )
            return result.rowcount
