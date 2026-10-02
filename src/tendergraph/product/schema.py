from __future__ import annotations

from psycopg_pool import ConnectionPool

CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS product;
"""

CREATE_ACCOUNTS_SQL = """
CREATE TABLE IF NOT EXISTS product.accounts (
    id UUID PRIMARY KEY,
    account_type TEXT NOT NULL DEFAULT 'local'
        CHECK (account_type IN ('local', 'registered')),
    email TEXT UNIQUE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (account_type <> 'local' OR email IS NULL)
);
"""

CREATE_EMAIL_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_accounts_email_lower
ON product.accounts (lower(email))
WHERE email IS NOT NULL;
"""

CREATE_PASSWORD_CREDENTIALS_SQL = """
CREATE TABLE IF NOT EXISTS product.password_credentials (
    account_id UUID PRIMARY KEY
        REFERENCES product.accounts(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_AUTH_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS product.auth_sessions (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL
        REFERENCES product.accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ
);
"""

CREATE_AUTH_SESSION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_auth_session_account_expiry
ON product.auth_sessions (account_id, expires_at DESC);
"""

CREATE_PROFILES_SQL = """
CREATE TABLE IF NOT EXISTS product.company_profiles (
    account_id UUID PRIMARY KEY
        REFERENCES product.accounts(id) ON DELETE CASCADE,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_OPPORTUNITIES_SQL = """
CREATE TABLE IF NOT EXISTS product.opportunity_states (
    account_id UUID NOT NULL
        REFERENCES product.accounts(id) ON DELETE CASCADE,
    publication_number TEXT NOT NULL,
    disposition TEXT NOT NULL
        CHECK (disposition IN ('saved', 'ignored')),
    pipeline_stage TEXT
        CHECK (
            pipeline_stage IS NULL
            OR pipeline_stage IN (
                'reviewing',
                'qualified',
                'bid',
                'no_bid'
            )
        ),
    note TEXT NOT NULL DEFAULT '',
    match_score DOUBLE PRECISION
        CHECK (
            match_score IS NULL
            OR (match_score >= 0 AND match_score <= 100)
        ),
    snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, publication_number),
    CHECK (
        (disposition = 'saved' AND pipeline_stage IS NOT NULL)
        OR
        (disposition = 'ignored' AND pipeline_stage IS NULL)
    )
);
"""

CREATE_OPPORTUNITY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_opportunity_account_updated
ON product.opportunity_states (account_id, updated_at DESC);
"""

SCHEMA_STATEMENTS = (
    CREATE_SCHEMA_SQL,
    CREATE_ACCOUNTS_SQL,
    CREATE_EMAIL_INDEX_SQL,
    CREATE_PASSWORD_CREDENTIALS_SQL,
    CREATE_AUTH_SESSIONS_SQL,
    CREATE_AUTH_SESSION_INDEX_SQL,
    CREATE_PROFILES_SQL,
    CREATE_OPPORTUNITIES_SQL,
    CREATE_OPPORTUNITY_INDEX_SQL,
)


def ensure_product_schema(pool: ConnectionPool) -> None:
    """Create the local-first product and authentication schema idempotently."""

    with pool.connection() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
