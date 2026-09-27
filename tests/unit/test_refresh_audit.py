import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tendergraph.pipeline.audit import (
    generate_refresh_id,
    new_refresh_audit,
    write_refresh_audit,
)

STARTED_AT = datetime(
    2026,
    9,
    27,
    15,
    30,
    45,
    123456,
    tzinfo=UTC,
)


def test_generate_refresh_id_is_deterministic() -> None:
    assert generate_refresh_id(
        started_at=STARTED_AT
    ) == (
        "20260927T153045123456Z"
    )


def test_generate_refresh_id_rejects_naive_time() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        generate_refresh_id(
            started_at=STARTED_AT.replace(
                tzinfo=None
            )
        )


def test_new_refresh_audit_starts_running() -> None:
    record = new_refresh_audit(
        start_date=date(
            2026,
            9,
            26,
        ),
        end_date=date(
            2026,
            9,
            27,
        ),
        countries=(
            "BEL",
            "NLD",
        ),
        started_at=STARTED_AT,
    )

    assert (
        record.refresh_id
        == "20260927T153045123456Z"
    )
    assert record.status == "running"
    assert record.finished_at_utc is None
    assert record.ingestion_run_id is None
    assert record.countries == (
        "BEL",
        "NLD",
    )


def test_write_refresh_audit_atomically(
    tmp_path: Path,
) -> None:
    record = new_refresh_audit(
        start_date=date(
            2026,
            9,
            27,
        ),
        end_date=date(
            2026,
            9,
            27,
        ),
        countries=("BEL",),
        started_at=STARTED_AT,
    )

    output = write_refresh_audit(
        record,
        root=tmp_path,
    )

    assert output == (
        tmp_path
        / record.refresh_id
        / "refresh_audit.json"
    )

    payload = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "running"
    assert payload["countries"] == [
        "BEL"
    ]

    assert not (
        output.parent
        / ".refresh_audit.json.tmp"
    ).exists()


def test_audit_record_can_be_updated_to_completed(
    tmp_path: Path,
) -> None:
    running = new_refresh_audit(
        start_date=date(
            2026,
            9,
            27,
        ),
        end_date=date(
            2026,
            9,
            27,
        ),
        countries=("BEL",),
        started_at=STARTED_AT,
    )

    write_refresh_audit(
        running,
        root=tmp_path,
    )

    completed = replace(
        running,
        status="completed",
        finished_at_utc=(
            "2026-09-27T15:31:00+00:00"
        ),
        ingestion_run_id="run-1",
        bronze_records_retrieved=12,
        silver_rows=12,
        inserted_rows=3,
        updated_rows=2,
        unchanged_rows=7,
        changed_publication_numbers=(
            "A",
            "B",
            "C",
            "D",
            "E",
        ),
        embedding_requested_rows=5,
        embedding_embedded_rows=5,
        dbt_success=True,
        dbt_elapsed_seconds=1.25,
        dbt_result_type=(
            "RunExecutionResult"
        ),
    )

    output = write_refresh_audit(
        completed,
        root=tmp_path,
    )

    payload = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert (
        payload["status"]
        == "completed"
    )
    assert payload["inserted_rows"] == 3
    assert payload["updated_rows"] == 2
    assert payload["dbt_success"] is True


def test_audit_record_can_capture_failure(
    tmp_path: Path,
) -> None:
    running = new_refresh_audit(
        start_date=date(
            2026,
            9,
            27,
        ),
        end_date=date(
            2026,
            9,
            27,
        ),
        countries=("ITA",),
        started_at=STARTED_AT,
    )

    failed = replace(
        running,
        status="failed",
        finished_at_utc=(
            "2026-09-27T15:31:00+00:00"
        ),
        failure_stage="embeddings",
        failure_type="RuntimeError",
        failure_message=(
            "embedding refresh failed"
        ),
    )

    output = write_refresh_audit(
        failed,
        root=tmp_path,
    )

    payload = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "failed"
    assert (
        payload["failure_stage"]
        == "embeddings"
    )
    assert (
        payload["failure_type"]
        == "RuntimeError"
    )
