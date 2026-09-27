from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

RefreshStatus = Literal[
    "running",
    "completed",
    "failed",
]

DEFAULT_REFRESH_AUDIT_ROOT = Path(
    "data/refresh/ted/runs"
)


def generate_refresh_id(
    *,
    started_at: datetime | None = None,
) -> str:
    timestamp = (
        started_at
        if started_at is not None
        else datetime.now(UTC)
    )

    if timestamp.tzinfo is None:
        raise ValueError(
            "started_at must be timezone-aware"
        )

    return timestamp.astimezone(
        UTC
    ).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )


@dataclass(frozen=True, slots=True)
class RefreshAuditRecord:
    refresh_id: str
    status: RefreshStatus

    started_at_utc: str
    finished_at_utc: str | None

    start_date: str
    end_date: str
    countries: tuple[str, ...]

    ingestion_run_id: str | None = None

    failure_stage: str | None = None
    failure_type: str | None = None
    failure_message: str | None = None

    bronze_source_matches: int | None = None
    bronze_records_retrieved: int | None = None
    bronze_unique_notices: int | None = None
    bronze_duplicate_notices: int | None = None

    silver_parquet_path: str | None = None
    silver_sha256: str | None = None
    silver_rows: int | None = None

    inserted_rows: int | None = None
    updated_rows: int | None = None
    unchanged_rows: int | None = None
    database_rows: int | None = None

    changed_publication_numbers: (
        tuple[str, ...] | None
    ) = None

    embedding_requested_rows: int | None = None
    embedding_embedded_rows: int | None = None
    embedding_inserted_rows: int | None = None
    embedding_updated_rows: int | None = None
    embedding_database_rows: int | None = None

    dbt_success: bool | None = None
    dbt_elapsed_seconds: float | None = None
    dbt_result_type: str | None = None


def new_refresh_audit(
    *,
    start_date: date,
    end_date: date,
    countries: tuple[str, ...],
    started_at: datetime | None = None,
) -> RefreshAuditRecord:
    timestamp = (
        started_at
        if started_at is not None
        else datetime.now(UTC)
    )

    if timestamp.tzinfo is None:
        raise ValueError(
            "started_at must be timezone-aware"
        )

    timestamp = timestamp.astimezone(
        UTC
    )

    return RefreshAuditRecord(
        refresh_id=generate_refresh_id(
            started_at=timestamp
        ),
        status="running",
        started_at_utc=timestamp.isoformat(),
        finished_at_utc=None,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        countries=countries,
    )


def write_refresh_audit(
    record: RefreshAuditRecord,
    *,
    root: Path = DEFAULT_REFRESH_AUDIT_ROOT,
) -> Path:
    output_dir = (
        Path(root)
        / record.refresh_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / "refresh_audit.json"
    )

    temporary_path = (
        output_dir
        / ".refresh_audit.json.tmp"
    )

    temporary_path.unlink(
        missing_ok=True
    )

    payload = asdict(
        record
    )

    try:
        temporary_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        json.loads(
            temporary_path.read_text(
                encoding="utf-8"
            )
        )

        temporary_path.replace(
            output_path
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True
        )
        raise

    return output_path
