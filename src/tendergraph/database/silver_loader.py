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

UPDATE_COLUMNS = tuple(
    column
    for column in COPY_COLUMNS
    if column != "publication_number"
)

# A new Bronze run_id alone must not make an
# otherwise identical tender look materially changed.
MATERIAL_COLUMNS = tuple(
    column
    for column in UPDATE_COLUMNS
    if column != "ingestion_run_id"
)

STAGE_TABLE_NAME = "_tendergraph_silver_stage"

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

# Backward-compatible migration for installations created
# before the enriched Silver schema. Empty arrays are valid
# normalized values for these optional repeated fields.
MIGRATE_TABLE_SQL = """
ALTER TABLE silver.tenders
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS description_language TEXT,
    ADD COLUMN IF NOT EXISTS lot_descriptions TEXT[] NOT NULL
        DEFAULT '{}'::TEXT[],
    ADD COLUMN IF NOT EXISTS lot_description_language TEXT,
    ADD COLUMN IF NOT EXISTS lot_description_text TEXT,
    ADD COLUMN IF NOT EXISTS procedure_type TEXT,
    ADD COLUMN IF NOT EXISTS contract_natures TEXT[] NOT NULL
        DEFAULT '{}'::TEXT[],
    ADD COLUMN IF NOT EXISTS deadlines TIMESTAMPTZ[] NOT NULL
        DEFAULT '{}'::TIMESTAMPTZ[],
    ADD COLUMN IF NOT EXISTS earliest_deadline TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS latest_deadline TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS estimated_value NUMERIC,
    ADD COLUMN IF NOT EXISTS estimated_value_currency TEXT,
    ADD COLUMN IF NOT EXISTS performance_countries TEXT[] NOT NULL
        DEFAULT '{}'::TEXT[],
    ADD COLUMN IF NOT EXISTS performance_regions TEXT[] NOT NULL
        DEFAULT '{}'::TEXT[];
"""


@dataclass(frozen=True, slots=True)
class LoadSummary:
    parquet_rows: int
    inserted_rows: int
    updated_rows: int
    unchanged_rows: int
    database_rows: int
    inserted_publication_numbers: tuple[str, ...]
    updated_publication_numbers: tuple[str, ...]

    @property
    def changed_publication_numbers(
        self,
    ) -> tuple[str, ...]:
        return (
            *self.inserted_publication_numbers,
            *self.updated_publication_numbers,
        )


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
    """Incrementally upsert validated Silver tenders."""

    frame = pl.read_parquet(
        parquet_path
    )

    quality = validate_silver_tenders(
        frame
    )

    expected_rows = quality.row_count

    column_list = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in COPY_COLUMNS
    )

    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN"
    ).format(
        sql.Identifier(STAGE_TABLE_NAME),
        column_list,
    )

    target_material = sql.SQL(", ").join(
        sql.SQL("target.{}").format(
            sql.Identifier(column)
        )
        for column in MATERIAL_COLUMNS
    )

    stage_material = sql.SQL(", ").join(
        sql.SQL("stage.{}").format(
            sql.Identifier(column)
        )
        for column in MATERIAL_COLUMNS
    )

    excluded_material = sql.SQL(", ").join(
        sql.SQL("EXCLUDED.{}").format(
            sql.Identifier(column)
        )
        for column in MATERIAL_COLUMNS
    )

    update_assignments = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(
            sql.Identifier(column),
            sql.Identifier(column),
        )
        for column in UPDATE_COLUMNS
    )

    create_stage_statement = sql.SQL(
        """
        CREATE TEMP TABLE {}
        ON COMMIT DROP
        AS
        SELECT {}
        FROM {}.{}
        WITH NO DATA
        """
    ).format(
        sql.Identifier(STAGE_TABLE_NAME),
        column_list,
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
    )

    inserted_ids_statement = sql.SQL(
        """
        SELECT stage.publication_number
        FROM {} AS stage
        LEFT JOIN {}.{} AS target
            ON target.publication_number
                = stage.publication_number
        WHERE target.publication_number IS NULL
        ORDER BY stage.publication_number
        """
    ).format(
        sql.Identifier(STAGE_TABLE_NAME),
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
    )

    updated_ids_statement = sql.SQL(
        """
        SELECT stage.publication_number
        FROM {} AS stage
        JOIN {}.{} AS target
            ON target.publication_number
                = stage.publication_number
        WHERE ROW({})
            IS DISTINCT FROM ROW({})
        ORDER BY stage.publication_number
        """
    ).format(
        sql.Identifier(STAGE_TABLE_NAME),
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
        target_material,
        stage_material,
    )

    upsert_statement = sql.SQL(
        """
        INSERT INTO {}.{} AS target ({})
        SELECT {}
        FROM {} AS stage
        ON CONFLICT (publication_number)
        DO UPDATE SET
            {},
            loaded_at = NOW()
        WHERE ROW({})
            IS DISTINCT FROM ROW({});
        """
    ).format(
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(TABLE_NAME),
        column_list,
        column_list,
        sql.Identifier(STAGE_TABLE_NAME),
        update_assignments,
        target_material,
        excluded_material,
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

        cursor.execute(
            MIGRATE_TABLE_SQL
        )

        cursor.execute(
            create_stage_statement
        )

        cursor.execute(
            sql.SQL(
                """
                ALTER TABLE {}
                ADD PRIMARY KEY (
                    publication_number
                )
                """
            ).format(
                sql.Identifier(
                    STAGE_TABLE_NAME
                )
            )
        )

        with cursor.copy(
            copy_statement
        ) as copy:
            for row in frame.iter_rows(
                named=True
            ):
                copy.write_row(
                    _row_values(row)
                )

        cursor.execute(
            sql.SQL(
                "SELECT COUNT(*) FROM {}"
            ).format(
                sql.Identifier(
                    STAGE_TABLE_NAME
                )
            )
        )

        stage_result = cursor.fetchone()

        if stage_result is None:
            raise RuntimeError(
                "Unable to verify Silver stage"
            )

        stage_rows = int(
            stage_result[0]
        )

        if stage_rows != expected_rows:
            raise RuntimeError(
                "Staged Silver row count mismatch: "
                f"{stage_rows} != {expected_rows}"
            )

        # Serialize competing Silver writers while keeping
        # readers available.
        cursor.execute(
            """
            LOCK TABLE silver.tenders
            IN SHARE ROW EXCLUSIVE MODE
            """
        )

        cursor.execute(
            inserted_ids_statement
        )

        inserted_publication_numbers = tuple(
            str(row[0])
            for row in cursor.fetchall()
        )

        cursor.execute(
            updated_ids_statement
        )

        updated_publication_numbers = tuple(
            str(row[0])
            for row in cursor.fetchall()
        )

        inserted_rows = len(
            inserted_publication_numbers
        )

        updated_rows = len(
            updated_publication_numbers
        )

        unchanged_rows = (
            expected_rows
            - inserted_rows
            - updated_rows
        )

        if unchanged_rows < 0:
            raise RuntimeError(
                "Incremental Silver classification "
                "produced invalid row counts"
            )

        cursor.execute(
            upsert_statement
        )

        affected_rows = cursor.rowcount

        if affected_rows != (
            inserted_rows + updated_rows
        ):
            raise RuntimeError(
                "UPSERT affected an unexpected "
                "number of rows: "
                f"{affected_rows} != "
                f"{inserted_rows + updated_rows}"
            )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM silver.tenders
            """
        )

        database_result = cursor.fetchone()

        if database_result is None:
            raise RuntimeError(
                "PostgreSQL count query "
                "returned no result"
            )

        database_rows = int(
            database_result[0]
        )

        cursor.execute(
            sql.SQL(
                """
                SELECT COUNT(*)
                FROM {}.{} AS target
                JOIN {} AS stage
                    ON target.publication_number
                        = stage.publication_number
                """
            ).format(
                sql.Identifier(SCHEMA_NAME),
                sql.Identifier(TABLE_NAME),
                sql.Identifier(
                    STAGE_TABLE_NAME
                ),
            )
        )

        matched_result = cursor.fetchone()

        if matched_result is None:
            raise RuntimeError(
                "Unable to verify incoming "
                "Silver rows"
            )

        matched_rows = int(
            matched_result[0]
        )

        if matched_rows != expected_rows:
            raise RuntimeError(
                "Not all incoming Silver rows "
                "exist after UPSERT: "
                f"{matched_rows} != "
                f"{expected_rows}"
            )

    return LoadSummary(
        parquet_rows=expected_rows,
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        unchanged_rows=unchanged_rows,
        database_rows=database_rows,
        inserted_publication_numbers=(
            inserted_publication_numbers
        ),
        updated_publication_numbers=(
            updated_publication_numbers
        ),
    )
