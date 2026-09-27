from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from tendergraph.pipeline.audit import (
    new_refresh_audit,
    write_refresh_audit,
)
from tendergraph.pipeline.status import (
    read_operational_status,
)


def completed_audit(
    *,
    started_at: datetime,
    end_date: date,
    dbt_success: bool = True,
    database_rows: int = 100,
):
    audit = new_refresh_audit(
        start_date=end_date,
        end_date=end_date,
        countries=("BEL",),
        started_at=started_at,
    )

    return replace(
        audit,
        status="completed",
        finished_at_utc=(
            started_at.isoformat()
        ),
        dbt_success=dbt_success,
        database_rows=database_rows,
        embedding_database_rows=(
            database_rows
        ),
    )


def test_status_is_ok_when_latest_success_is_fresh(
    tmp_path: Path,
) -> None:
    audit = completed_audit(
        started_at=datetime(
            2026,
            9,
            27,
            8,
            30,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
    )

    write_refresh_audit(
        audit,
        root=tmp_path,
    )

    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert status.overall_status == "ok"
    assert status.stale is False
    assert status.lag_days == 0
    assert (
        status.last_successful_window_end
        == date(2026, 9, 26)
    )
    assert (
        status.last_success_database_rows
        == 100
    )


def test_status_is_stale_when_success_lags(
    tmp_path: Path,
) -> None:
    audit = completed_audit(
        started_at=datetime(
            2026,
            9,
            25,
            8,
            30,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            24,
        ),
    )

    write_refresh_audit(
        audit,
        root=tmp_path,
    )

    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert (
        status.overall_status
        == "stale"
    )
    assert status.stale is True
    assert status.lag_days == 2


def test_failed_latest_run_is_degraded(
    tmp_path: Path,
) -> None:
    success = completed_audit(
        started_at=datetime(
            2026,
            9,
            27,
            8,
            0,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
    )

    write_refresh_audit(
        success,
        root=tmp_path,
    )

    failed = new_refresh_audit(
        start_date=date(
            2026,
            9,
            26,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
        countries=("BEL",),
        started_at=datetime(
            2026,
            9,
            27,
            9,
            0,
            tzinfo=UTC,
        ),
    )

    failed = replace(
        failed,
        status="failed",
        finished_at_utc=(
            "2026-09-27T09:01:00+00:00"
        ),
        failure_stage="ingestion",
        failure_type="RuntimeError",
    )

    write_refresh_audit(
        failed,
        root=tmp_path,
    )

    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert (
        status.overall_status
        == "degraded"
    )
    assert status.stale is False
    assert (
        status.latest_refresh_status
        == "failed"
    )
    assert (
        status.failure_stage
        == "ingestion"
    )
    assert (
        status.failure_type
        == "RuntimeError"
    )
    assert (
        status.last_successful_refresh_id
        == success.refresh_id
    )


def test_running_latest_run_is_refreshing(
    tmp_path: Path,
) -> None:
    success = completed_audit(
        started_at=datetime(
            2026,
            9,
            27,
            8,
            0,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
    )

    write_refresh_audit(
        success,
        root=tmp_path,
    )

    running = new_refresh_audit(
        start_date=date(
            2026,
            9,
            26,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
        countries=("BEL",),
        started_at=datetime(
            2026,
            9,
            27,
            9,
            0,
            tzinfo=UTC,
        ),
    )

    write_refresh_audit(
        running,
        root=tmp_path,
    )

    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert (
        status.overall_status
        == "refreshing"
    )
    assert status.stale is False
    assert (
        status.latest_refresh_status
        == "running"
    )


def test_missing_history_is_unknown(
    tmp_path: Path,
) -> None:
    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert (
        status.overall_status
        == "unknown"
    )
    assert status.stale is True
    assert status.lag_days is None
    assert (
        status.latest_refresh_id
        is None
    )


def test_status_carries_forward_known_row_counts(
    tmp_path: Path,
) -> None:
    previous = completed_audit(
        started_at=datetime(
            2026,
            9,
            27,
            7,
            0,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
        database_rows=5819,
    )

    write_refresh_audit(
        previous,
        root=tmp_path,
    )

    latest = completed_audit(
        started_at=datetime(
            2026,
            9,
            27,
            8,
            30,
            tzinfo=UTC,
        ),
        end_date=date(
            2026,
            9,
            26,
        ),
        database_rows=5819,
    )

    latest = replace(
        latest,
        embedding_database_rows=None,
    )

    write_refresh_audit(
        latest,
        root=tmp_path,
    )

    status = read_operational_status(
        root=tmp_path,
        now=datetime(
            2026,
            9,
            27,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    assert (
        status.last_success_database_rows
        == 5819
    )
    assert (
        status.last_success_embedding_rows
        == 5819
    )
