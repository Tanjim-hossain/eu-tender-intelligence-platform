from __future__ import annotations

from psycopg_pool import ConnectionPool

CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS documents;
"""

CREATE_PACKAGES_SQL = """
CREATE TABLE IF NOT EXISTS documents.packages (
    publication_number TEXT PRIMARY KEY,
    title TEXT,
    source_xml_url TEXT,
    package_status TEXT NOT NULL
        CHECK (package_status IN (
            'not_ingested',
            'ingested',
            'partial',
            'restricted_only',
            'failed'
        )),
    xml_sha256 TEXT,
    error TEXT,
    discovered_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_ASSETS_SQL = """
CREATE TABLE IF NOT EXISTS documents.assets (
    publication_number TEXT NOT NULL,
    document_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    restricted BOOLEAN NOT NULL DEFAULT FALSE,
    restriction_code TEXT,
    official_languages TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    unofficial_languages TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    status TEXT NOT NULL
        CHECK (status IN (
            'discovered',
            'restricted',
            'extracted',
            'fetched',
            'unsupported',
            'access_denied',
            'failed'
        )),
    final_url TEXT,
    content_type TEXT,
    byte_count BIGINT CHECK (byte_count IS NULL OR byte_count >= 0),
    sha256 TEXT,
    cache_path TEXT,
    extraction_method TEXT,
    extracted_text TEXT,
    error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (publication_number, document_id),
    FOREIGN KEY (publication_number)
        REFERENCES documents.packages(publication_number)
        ON DELETE CASCADE
);
"""

CREATE_ASSET_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_documents_assets_publication_status
ON documents.assets (publication_number, status);
"""

SCHEMA_STATEMENTS = (
    CREATE_SCHEMA_SQL,
    CREATE_PACKAGES_SQL,
    CREATE_ASSETS_SQL,
    CREATE_ASSET_INDEX_SQL,
)


def ensure_documents_schema(pool: ConnectionPool) -> None:
    """Create procurement-document persistence tables idempotently."""

    with pool.connection() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
