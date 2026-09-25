from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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

    buyer_name TEXT,
    buyer_name_language TEXT,

    buyer_countries TEXT[] NOT NULL,
    first_buyer_country TEXT NOT NULL,

    cpv_codes TEXT[] NOT NULL,
    first_cpv_code TEXT,

    source_html_url TEXT NOT NULL,
    source_xml_url TEXT,

    ingestion_run_id TEXT NOT NULL,
    source TEXT NOT NULL,

    loaded_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True, slots=True)
class LoadSummary:
    parquet_rows: int
    inserted_rows: int
    database_rows: int


def _row_values(
    row: dict[str, Any],
) -> tuple[object, ...]:
    publication_date = row["publication_date"]

    if not isinstance(publication_date, date):
        raise TypeError(
            "publication_date must be a date"
        )

    return (
        row["publication_number"],
        publication_date,
        row["publication_date_raw"],
        row["notice_type"],
        row["title"],
        row["title_language"],
        row["buyer_name"],
        row["buyer_name_language"],
        row["buyer_countries"],
        row["first_buyer_country"],
        row["cpv_codes"],
        row["first_cpv_code"],
        row["source_html_url"],
        row["source_xml_url"],
        row["ingestion_run_id"],
        row["source"],
    )


def load_silver_tenders(
    parquet_path: Path,
    settings: DatabaseSettings,
) -> LoadSummary:
    """Atomically replace PostgreSQL Silver tenders."""

    frame = pl.read_parquet(parquet_path)

    quality = validate_silver_tenders(frame)

    expected_rows = quality.row_count

    columns = [
        "publication_number",
        "publication_date",
        "publication_date_raw",
        "notice_type",
        "title",
        "title_language",
        "buyer_name",
        "buyer_name_language",
        "buyer_countries",
        "first_buyer_country",
        "cpv_codes",
        "first_cpv_code",
        "source_html_url",
        "source_xml_url",
        "ingestion_run_id",
        "source",
    ]

    copy_statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN"
    ).format(
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
        sql.SQL(", ").join(
            sql.Identifier(column)
            for column in columns
        ),
    )

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(CREATE_SCHEMA_SQL)
        cursor.execute(CREATE_TABLE_SQL)

        # Transactional replacement:
        # if COPY or validation fails,
        # PostgreSQL rolls the TRUNCATE back too.
        cursor.execute(
            "TRUNCATE TABLE silver.tenders"
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

        database_rows = int(result[0])

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
