from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from tendergraph.cli.refresh import main as refresh_main
from tendergraph.ingestion.window import (
    DEFAULT_COUNTRIES,
    normalize_country_codes,
)

DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_END_LAG_DAYS = 1


def _positive_int(value: str) -> int:
    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError(
            "value must be >= 1"
        )

    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be >= 0"
        )

    return parsed


def build_scheduled_window(
    *,
    as_of_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    end_lag_days: int = DEFAULT_END_LAG_DAYS,
) -> tuple[date, date]:
    """Build an inclusive trailing publication window."""

    if lookback_days < 1:
        raise ValueError(
            "lookback_days must be >= 1"
        )

    if end_lag_days < 0:
        raise ValueError(
            "end_lag_days must be >= 0"
        )

    end_date = (
        as_of_date
        - timedelta(
            days=end_lag_days
        )
    )

    start_date = (
        end_date
        - timedelta(
            days=lookback_days - 1
        )
    )

    return start_date, end_date


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a scheduled TenderGraph refresh "
            "using a trailing UTC publication window."
        )
    )

    parser.add_argument(
        "--lookback-days",
        type=_positive_int,
        default=DEFAULT_LOOKBACK_DAYS,
        metavar="N",
        help=(
            "Inclusive publication-window length "
            "(default: 3)."
        ),
    )

    parser.add_argument(
        "--end-lag-days",
        type=_non_negative_int,
        default=DEFAULT_END_LAG_DAYS,
        metavar="N",
        help=(
            "Days before UTC today used as the "
            "window end (default: 1)."
        ),
    )

    parser.add_argument(
        "--countries",
        nargs="+",
        default=list(
            DEFAULT_COUNTRIES
        ),
        metavar="ISO3",
        help=(
            "Buyer-country ISO3 codes. "
            "Default: BEL NLD DEU ITA."
        ),
    )

    args = parser.parse_args(
        argv
    )

    try:
        args.countries = list(
            normalize_country_codes(
                args.countries
            )
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    return args


def main(
    argv: Sequence[str] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    args = parse_args(
        argv
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

    start_date, end_date = (
        build_scheduled_window(
            as_of_date=utc_today,
            lookback_days=(
                args.lookback_days
            ),
            end_lag_days=(
                args.end_lag_days
            ),
        )
    )

    print(
        "=== TENDERGRAPH SCHEDULED REFRESH ==="
    )
    print(
        f"UTC today:      "
        f"{utc_today.isoformat()}"
    )
    print(
        f"Lookback days:  "
        f"{args.lookback_days}"
    )
    print(
        f"End lag days:   "
        f"{args.end_lag_days}"
    )
    print(
        f"Window:         "
        f"{start_date.isoformat()} "
        f"to {end_date.isoformat()}"
    )
    print()

    refresh_argv = [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--countries",
        *args.countries,
    ]

    return refresh_main(
        refresh_argv
    )
