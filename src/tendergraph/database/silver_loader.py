from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import psycopg
from psycopg import sql

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.processing.quality import (
    validate_silver_tenders,
)

SCHEMA_NAME = "silver"
TABLE_NAME = "tenders"

COPY_COLUMNS = (
    "publication_number",
    "publication_date",
    "publication_date_raw",
    "notice_type",
    "title",
    "title_language",
    "description",
    "description_language",
    "lot_descriptions",
    "lot_description_language",
    "lot_description_text",
    "buyer_name",
    "buyer_name_language",
    "buyer_countries",
    "first_buyer_country",
    "cpv_codes",
    "first_cpv_code",
    "procedure_type",
    "contract_natures",
    "deadlines",
    "earliest_deadline",
    "latest_deadline",
    "estimated_value",
    "estimated_value_currency",
    "performance_countries",
    "performance_regions",
    "source_html_url",
    "source_xml_url",
    "ingestion_run_id",
    "source",
)

CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS silver;
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS silver.tenders (
    publication_number TEXT PRIMARY KEY,
    publication_date DATE NOT NULL,
    publication_date_raw TEXT NOT NULL,
    notice_type TEXT NOT NULL,
    title TEXT NOT NULL,
    title_language TEXT,

    description TEXT,
    description_language TEXT,
    lot_descriptions TEXT[] NOT NULL,
    lot_description_language TEXT,
    lot_description_text TEXT,

    buyer_name TEXT,
    buyer_name_language TEXT,
    buyer_countries TEXT[] NOT NULL,
    first_buyer_country TEXT NOT NULL,

    cpv_codes TEXT[] NOT NULL,
    first_cpv_code TEXT,

    procedure_type TEXT,
    contract_natures TEXT[] NOT NULL,

    deadlines TIMESTAMPTZ[] NOT NULL,
    earliest_deadline TIMESTAMPTZ,
    latest_deadline TIMESTAMPTZ,

    estimated_value NUMERIC,
    estimated_value_currency TEXT,

    performance_countries TEXT[] NOT NULL,
    performance_regions TEXT[] NOT NULL,

    source_html_url TEXT NOT NULL,
    source_xml_url TEXT,

    ingestion_run_id TEXT NOT NULL,
    source TEXT NOT NULL,

    loaded_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
"""

# The original v1 table already exists on upgraded
# installations. The table is truncated before this
# migration, so new NOT NULL array columns can be added
# safely without synthetic defaults.
MIGRATE_TABLE_SQL = """
ALTER TABLE silver.tenders
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS description_language TEXT,
    ADD COLUMN IF NOT EXISTS lot_descriptions TEXT[] NOT NULL,
    ADD COLUMN IF NOT EXISTS lot_description_language TEXT,
    ADD COLUMN IF NOT EXISTS lot_description_text TEXT,
    ADD COLUMN IF NOT EXISTS procedure_type TEXT,
    ADD COLUMN IF NOT EXISTS contract_natures TEXT[] NOT NULL,
    ADD COLUMN IF NOT EXISTS deadlines TIMESTAMPTZ[] NOT NULL,
    ADD COLUMN IF NOT EXISTS earliest_deadline TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS latest_deadline TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS estimated_value NUMERIC,
    ADD COLUMN IF NOT EXISTS estimated_value_currency TEXT,
    ADD COLUMN IF NOT EXISTS performance_countries TEXT[] NOT NULL,
    ADD COLUMN IF NOT EXISTS performance_regions TEXT[] NOT NULL;
"""


@dataclass(frozen=True, slots=True)
class LoadSummary:
    parquet_rows: int
    inserted_rows: int
    database_rows: int


def _validate_utc_datetime(
    value: object,
    *,
    field_name: str,
) -> None:
    if value is None:
        return

    if not isinstance(value, datetime):
        raise TypeError(
            f"{field_name} must be a datetime or None"
        )

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise TypeError(
            f"{field_name} must be timezone-aware"
        )

    if value.utcoffset() != timedelta(0):
        raise ValueError(
            f"{field_name} must be normalized to UTC"
        )


def _row_values(
    row: dict[str, Any],
) -> tuple[object, ...]:
    publication_date = row["publication_date"]

    if type(publication_date) is not date:
        raise TypeError(
            "publication_date must be a date"
        )

    deadlines = row["deadlines"]

    if not isinstance(deadlines, list):
        raise TypeError(
            "deadlines must be a list"
        )

    for deadline in deadlines:
        _validate_utc_datetime(
            deadline,
            field_name="deadline",
        )

    _validate_utc_datetime(
        row["earliest_deadline"],
        field_name="earliest_deadline",
    )

    _validate_utc_datetime(
        row["latest_deadline"],
        field_name="latest_deadline",
    )

    estimated_value = row["estimated_value"]

    if (
        estimated_value is not None
        and not isinstance(
            estimated_value,
            Decimal,
        )
    ):
        raise TypeError(
            "estimated_value must be "
            "Decimal or None"
        )

    return tuple(
        row[column]
        for column in COPY_COLUMNS
    )


def load_silver_tenders(
    parquet_path: Path,
    settings: DatabaseSettings,
) -> LoadSummary:
    """Atomically replace PostgreSQL Silver tenders."""

    frame = pl.read_parquet(
        parquet_path
    )

    quality = validate_silver_tenders(
        frame
    )

    expected_rows = quality.row_count

    copy_statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN"
    ).format(
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
        sql.SQL(", ").join(
            sql.Identifier(column)
            for column in COPY_COLUMNS
        ),
    )

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            CREATE_SCHEMA_SQL
        )

        cursor.execute(
            CREATE_TABLE_SQL
        )

        # Keep the migration and replacement in one
        # transaction. Any later failure rolls both
        # schema changes and TRUNCATE back.
        cursor.execute(
            "TRUNCATE TABLE silver.tenders"
        )

        cursor.execute(
            MIGRATE_TABLE_SQL
        )

        inserted_rows = 0

        with cursor.copy(
            copy_statement
        ) as copy:
            for row in frame.iter_rows(
                named=True
            ):
                copy.write_row(
                    _row_values(row)
                )

                inserted_rows += 1

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM silver.tenders
            """
        )

        result = cursor.fetchone()

        if result is None:
            raise RuntimeError(
                "PostgreSQL count query "
                "returned no result"
            )

        database_rows = int(
            result[0]
        )

        if inserted_rows != expected_rows:
            raise RuntimeError(
                "Loader inserted an unexpected "
                "number of rows: "
                f"{inserted_rows} != "
                f"{expected_rows}"
            )

        if database_rows != expected_rows:
            raise RuntimeError(
                "PostgreSQL row count does not "
                "match Silver dataset: "
                f"{database_rows} != "
                f"{expected_rows}"
            )

    return LoadSummary(
        parquet_rows=expected_rows,
        inserted_rows=inserted_rows,
        database_rows=database_rows,
    )
