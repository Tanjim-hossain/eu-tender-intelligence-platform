from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from tendergraph.pipeline.audit import (
    DEFAULT_REFRESH_AUDIT_ROOT,
    RefreshStatus,
)

OverallStatus = Literal[
    "ok",
    "refreshing",
    "degraded",
    "stale",
    "unknown",
]

DEFAULT_EXPECTED_END_LAG_DAYS = 1


@dataclass(frozen=True, slots=True)
class OperationalStatus:
    overall_status: OverallStatus

    latest_refresh_id: str | None
    latest_refresh_status: RefreshStatus | None
    latest_started_at_utc: datetime | None
    latest_finished_at_utc: datetime | None
    latest_window_end: date | None
    latest_dbt_success: bool | None

    last_successful_refresh_id: str | None
    last_successful_finished_at_utc: datetime | None
    last_successful_window_end: date | None

    expected_data_through: date
    lag_days: int | None
    stale: bool

    last_success_database_rows: int | None
    last_success_embedding_rows: int | None

    failure_stage: str | None
    failure_type: str | None


@dataclass(frozen=True, slots=True)
class _AuditSnapshot:
    refresh_id: str
    status: RefreshStatus

    started_at_utc: datetime
    finished_at_utc: datetime | None
    end_date: date

    dbt_success: bool | None
    database_rows: int | None
    embedding_database_rows: int | None

    failure_stage: str | None
    failure_type: str | None


def _required_string(
    payload: dict[str, object],
    field: str,
) -> str:
    value = payload.get(field)

    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Audit field {field!r} must be "
            "a non-empty string"
        )

    return value


def _optional_string(
    payload: dict[str, object],
    field: str,
) -> str | None:
    value = payload.get(field)

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"Audit field {field!r} must be "
            "a string or null"
        )

    return value


def _optional_bool(
    payload: dict[str, object],
    field: str,
) -> bool | None:
    value = payload.get(field)

    if value is None:
        return None

    if type(value) is not bool:
        raise ValueError(
            f"Audit field {field!r} must be "
            "a boolean or null"
        )

    return value


def _optional_int(
    payload: dict[str, object],
    field: str,
) -> int | None:
    value = payload.get(field)

    if value is None:
        return None

    if type(value) is not int:
        raise ValueError(
            f"Audit field {field!r} must be "
            "an integer or null"
        )

    return value


def _parse_datetime(
    value: str | None,
    *,
    field: str,
) -> datetime | None:
    if value is None:
        return None

    try:
        parsed = datetime.fromisoformat(
            value
        )
    except ValueError as exc:
        raise ValueError(
            f"Audit field {field!r} is not "
            "a valid ISO datetime"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            f"Audit field {field!r} must be "
            "timezone-aware"
        )

    return parsed.astimezone(UTC)


def _parse_date(
    value: str,
    *,
    field: str,
) -> date:
    try:
        return date.fromisoformat(
            value
        )
    except ValueError as exc:
        raise ValueError(
            f"Audit field {field!r} is not "
            "a valid ISO date"
        ) from exc


def _read_audit(
    path: Path,
) -> _AuditSnapshot:
    payload_raw = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload_raw,
        dict,
    ):
        raise TypeError(
            "Refresh audit must contain "
            "a JSON object"
        )

    payload = cast(
        dict[str, object],
        payload_raw,
    )

    status_value = _required_string(
        payload,
        "status",
    )

    if status_value not in {
        "running",
        "completed",
        "failed",
    }:
        raise ValueError(
            "Unknown refresh audit status: "
            f"{status_value}"
        )

    status = cast(
        RefreshStatus,
        status_value,
    )

    started_at = _parse_datetime(
        _required_string(
            payload,
            "started_at_utc",
        ),
        field="started_at_utc",
    )

    if started_at is None:
        raise RuntimeError(
            "started_at_utc unexpectedly missing"
        )

    return _AuditSnapshot(
        refresh_id=_required_string(
            payload,
            "refresh_id",
        ),
        status=status,
        started_at_utc=started_at,
        finished_at_utc=_parse_datetime(
            _optional_string(
                payload,
                "finished_at_utc",
            ),
            field="finished_at_utc",
        ),
        end_date=_parse_date(
            _required_string(
                payload,
                "end_date",
            ),
            field="end_date",
        ),
        dbt_success=_optional_bool(
            payload,
            "dbt_success",
        ),
        database_rows=_optional_int(
            payload,
            "database_rows",
        ),
        embedding_database_rows=(
            _optional_int(
                payload,
                "embedding_database_rows",
            )
        ),
        failure_stage=_optional_string(
            payload,
            "failure_stage",
        ),
        failure_type=_optional_string(
            payload,
            "failure_type",
        ),
    )


def read_operational_status(
    *,
    root: Path = DEFAULT_REFRESH_AUDIT_ROOT,
    now: datetime | None = None,
    expected_end_lag_days: int = (
        DEFAULT_EXPECTED_END_LAG_DAYS
    ),
) -> OperationalStatus:
    if expected_end_lag_days < 0:
        raise ValueError(
            "expected_end_lag_days must be >= 0"
        )

    timestamp = (
        now
        if now is not None
        else datetime.now(UTC)
    )

    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise ValueError(
            "now must be timezone-aware"
        )

    utc_today = (
        timestamp
        .astimezone(UTC)
        .date()
    )

    expected_data_through = (
        utc_today
        - timedelta(
            days=expected_end_lag_days
        )
    )

    paths = sorted(
        Path(root).glob(
            "*/refresh_audit.json"
        )
    )

    if not paths:
        return OperationalStatus(
            overall_status="unknown",
            latest_refresh_id=None,
            latest_refresh_status=None,
            latest_started_at_utc=None,
            latest_finished_at_utc=None,
            latest_window_end=None,
            latest_dbt_success=None,
            last_successful_refresh_id=None,
            last_successful_finished_at_utc=None,
            last_successful_window_end=None,
            expected_data_through=(
                expected_data_through
            ),
            lag_days=None,
            stale=True,
            last_success_database_rows=None,
            last_success_embedding_rows=None,
            failure_stage=None,
            failure_type=None,
        )

    audits = [
        _read_audit(path)
        for path in paths
    ]

    audits.sort(
        key=lambda audit: (
            audit.started_at_utc
        )
    )

    latest = audits[-1]

    successful = [
        audit
        for audit in audits
        if (
            audit.status == "completed"
            and audit.dbt_success is True
        )
    ]

    last_success = (
        successful[-1]
        if successful
        else None
    )

    latest_known_database_rows = next(
        (
            audit.database_rows
            for audit in reversed(successful)
            if audit.database_rows is not None
        ),
        None,
    )

    latest_known_embedding_rows = next(
        (
            audit.embedding_database_rows
            for audit in reversed(successful)
            if (
                audit.embedding_database_rows
                is not None
            )
        ),
        None,
    )

    if last_success is None:
        stale = True
        lag_days = None
    else:
        lag_days = max(
            (
                expected_data_through
                - last_success.end_date
            ).days,
            0,
        )
        stale = lag_days > 0

    if latest.status == "running":
        overall_status: OverallStatus = (
            "refreshing"
        )
    elif (
        latest.status == "failed"
        or latest.dbt_success is False
    ):
        overall_status = "degraded"
    elif stale:
        overall_status = "stale"
    else:
        overall_status = "ok"

    return OperationalStatus(
        overall_status=overall_status,
        latest_refresh_id=(
            latest.refresh_id
        ),
        latest_refresh_status=(
            latest.status
        ),
        latest_started_at_utc=(
            latest.started_at_utc
        ),
        latest_finished_at_utc=(
            latest.finished_at_utc
        ),
        latest_window_end=(
            latest.end_date
        ),
        latest_dbt_success=(
            latest.dbt_success
        ),
        last_successful_refresh_id=(
            last_success.refresh_id
            if last_success is not None
            else None
        ),
        last_successful_finished_at_utc=(
            last_success.finished_at_utc
            if last_success is not None
            else None
        ),
        last_successful_window_end=(
            last_success.end_date
            if last_success is not None
            else None
        ),
        expected_data_through=(
            expected_data_through
        ),
        lag_days=lag_days,
        stale=stale,
        last_success_database_rows=(
            latest_known_database_rows
        ),
        last_success_embedding_rows=(
            latest_known_embedding_rows
        ),
        failure_stage=(
            latest.failure_stage
            if latest.status == "failed"
            else None
        ),
        failure_type=(
            latest.failure_type
            if latest.status == "failed"
            else None
        ),
    )
