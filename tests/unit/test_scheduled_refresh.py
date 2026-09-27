from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from tendergraph.cli.scheduled_refresh import (
    build_scheduled_window,
    main,
    parse_args,
)


def test_default_window_ends_yesterday() -> None:
    start_date, end_date = (
        build_scheduled_window(
            as_of_date=date(
                2026,
                9,
                28,
            )
        )
    )

    assert start_date == date(
        2026,
        9,
        25,
    )
    assert end_date == date(
        2026,
        9,
        27,
    )


def test_window_supports_same_day_refresh() -> None:
    start_date, end_date = (
        build_scheduled_window(
            as_of_date=date(
                2026,
                9,
                28,
            ),
            lookback_days=1,
            end_lag_days=0,
        )
    )

    assert start_date == date(
        2026,
        9,
        28,
    )
    assert end_date == date(
        2026,
        9,
        28,
    )


def test_parse_rejects_zero_lookback() -> None:
    with pytest.raises(
        SystemExit
    ):
        parse_args(
            [
                "--lookback-days",
                "0",
            ]
        )


def test_main_forwards_scheduled_window(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch(
        "tendergraph.cli.scheduled_refresh."
        "refresh_main",
        return_value=0,
    ) as refresh_main:
        status = main(
            [
                "--countries",
                "BEL",
                "ITA",
            ],
            now=datetime(
                2026,
                9,
                28,
                8,
                30,
                tzinfo=UTC,
            ),
        )

    assert status == 0

    refresh_main.assert_called_once_with(
        [
            "--start-date",
            "2026-09-25",
            "--end-date",
            "2026-09-27",
            "--countries",
            "BEL",
            "ITA",
        ]
    )

    output = (
        capsys
        .readouterr()
        .out
    )

    assert (
        "2026-09-25 to 2026-09-27"
        in output
    )


def test_main_rejects_naive_clock() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        main(
            [],
            now=datetime(
                2026,
                9,
                28,
                8,
                30,
                tzinfo=UTC,
            ).replace(
                tzinfo=None
            ),
        )
