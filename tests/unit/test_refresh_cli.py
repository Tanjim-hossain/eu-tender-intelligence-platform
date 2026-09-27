from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tendergraph.cli.refresh import (
    main,
    parse_args,
)


def fake_summary() -> SimpleNamespace:
    ingestion = SimpleNamespace(
        records_retrieved=12
    )

    silver_artifact = SimpleNamespace(
        row_count=12,
        parquet_path=Path(
            "data/silver/ted/runs/"
            "run-1/tenders.parquet"
        ),
    )

    silver_load = SimpleNamespace(
        inserted_rows=3,
        updated_rows=2,
        unchanged_rows=7,
        database_rows=4890,
    )

    embeddings = SimpleNamespace(
        embedded_rows=5
    )

    refresh = SimpleNamespace(
        ingestion=ingestion,
        silver_artifact=(
            silver_artifact
        ),
        silver_load=silver_load,
        embeddings=embeddings,
        changed_rows=5,
    )

    dbt = SimpleNamespace(
        success=True
    )

    return SimpleNamespace(
        refresh_id="refresh-1",
        run_id="run-1",
        refresh=refresh,
        dbt=dbt,
        audit_path=Path(
            "data/refresh/ted/runs/"
            "refresh-1/"
            "refresh_audit.json"
        ),
    )


def test_parse_args_uses_default_countries() -> None:
    args = parse_args(
        [
            "--start-date",
            "2026-09-27",
            "--end-date",
            "2026-09-27",
        ]
    )

    assert args.countries == [
        "BEL",
        "NLD",
        "DEU",
        "ITA",
    ]

    assert (
        args.embedding_batch_size
        == 32
    )


def test_parse_args_normalizes_countries() -> None:
    args = parse_args(
        [
            "--start-date",
            "2026-09-27",
            "--end-date",
            "2026-09-27",
            "--countries",
            "bel",
            "ita",
        ]
    )

    assert args.countries == [
        "BEL",
        "ITA",
    ]


def test_parse_args_rejects_reverse_window() -> None:
    with pytest.raises(
        SystemExit,
    ):
        parse_args(
            [
                "--start-date",
                "2026-09-28",
                "--end-date",
                "2026-09-27",
            ]
        )


def test_parse_args_requires_positive_batch_size() -> None:
    with pytest.raises(
        SystemExit,
    ):
        parse_args(
            [
                "--start-date",
                "2026-09-27",
                "--end-date",
                "2026-09-27",
                "--embedding-batch-size",
                "0",
            ]
        )


def test_main_runs_operational_refresh(
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = fake_summary()

    with patch(
        "tendergraph.cli.refresh."
        "run_operational_refresh",
        return_value=summary,
    ) as run_refresh:
        status = main(
            [
                "--start-date",
                "2026-09-27",
                "--end-date",
                "2026-09-27",
                "--countries",
                "BEL",
                "ITA",
                "--embedding-batch-size",
                "16",
            ]
        )

    assert status == 0

    run_refresh.assert_called_once()

    kwargs = (
        run_refresh.call_args.kwargs
    )

    assert (
        kwargs["start_date"].isoformat()
        == "2026-09-27"
    )

    assert (
        kwargs["end_date"].isoformat()
        == "2026-09-27"
    )

    assert kwargs["countries"] == [
        "BEL",
        "ITA",
    ]

    assert (
        kwargs["embedding_batch_size"]
        == 16
    )

    output = capsys.readouterr().out

    assert (
        "REFRESH COMPLETED"
        in output
    )
    assert "run-1" in output
    assert "Changed rows:      5" in output
    assert "dbt success:       True" in output
