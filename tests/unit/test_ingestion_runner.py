from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tendergraph.ingestion.runner import (
    ingest_ted_window,
)
from tendergraph.storage.iteration_run import (
    BronzeRunArtifact,
)


def notice(
    publication_number: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        publication_number=publication_number
    )


def page(
    *,
    page_number: int,
    total: int,
    publications: list[str],
) -> SimpleNamespace:
    parsed = SimpleNamespace(
        total_notice_count=total,
        notices=[
            notice(value)
            for value in publications
        ],
    )

    result = SimpleNamespace(
        parsed=parsed
    )

    return SimpleNamespace(
        page_number=page_number,
        result=result,
    )


def test_ingest_window_returns_completed_run() -> None:
    client = Mock()
    writer = Mock()

    client.iterate.return_value = [
        page(
            page_number=1,
            total=3,
            publications=[
                "A",
                "B",
            ],
        ),
        page(
            page_number=2,
            total=3,
            publications=[
                "C",
            ],
        ),
    ]

    writer.write_page.side_effect = [
        SimpleNamespace(
            sha256="a" * 64
        ),
        SimpleNamespace(
            sha256="b" * 64
        ),
    ]

    artifact = BronzeRunArtifact(
        run_id="run-1",
        run_dir=Path(
            "data/bronze/run-1"
        ),
        manifest_path=Path(
            "data/bronze/run-1/"
            "run_manifest.json"
        ),
        page_count=2,
        record_count=3,
        status="completed",
    )

    writer.finalize.return_value = (
        artifact
    )

    result = ingest_ted_window(
        start_date=date(
            2026,
            9,
            18,
        ),
        end_date=date(
            2026,
            9,
            18,
        ),
        countries=[
            "BEL",
        ],
        client=client,
        writer=writer,
    )

    assert (
        result.run_artifact
        == artifact
    )
    assert (
        result.total_source_matches
        == 3
    )
    assert (
        result.records_retrieved
        == 3
    )
    assert (
        result.unique_publication_numbers
        == 3
    )
    assert (
        result.duplicate_publication_numbers
        == 0
    )

    finalize = (
        writer.finalize.call_args.kwargs
    )

    assert (
        finalize["status"]
        == "completed"
    )


def test_ingest_window_counts_duplicates() -> None:
    client = Mock()
    writer = Mock()

    client.iterate.return_value = [
        page(
            page_number=1,
            total=3,
            publications=[
                "A",
                "A",
                "B",
            ],
        ),
    ]

    writer.write_page.return_value = (
        SimpleNamespace(
            sha256="a" * 64
        )
    )

    writer.finalize.return_value = (
        BronzeRunArtifact(
            run_id="run-1",
            run_dir=Path(
                "data/bronze/run-1"
            ),
            manifest_path=Path(
                "data/bronze/run-1/"
                "run_manifest.json"
            ),
            page_count=1,
            record_count=3,
            status="completed",
        )
    )

    result = ingest_ted_window(
        start_date=date(
            2026,
            9,
            18,
        ),
        end_date=date(
            2026,
            9,
            18,
        ),
        countries=["BEL"],
        client=client,
        writer=writer,
    )

    assert (
        result.unique_publication_numbers
        == 2
    )
    assert (
        result.duplicate_publication_numbers
        == 1
    )


def test_ingest_window_marks_incomplete_run_failed() -> None:
    client = Mock()
    writer = Mock()

    client.iterate.return_value = [
        page(
            page_number=1,
            total=3,
            publications=[
                "A",
                "B",
            ],
        ),
    ]

    writer.write_page.return_value = (
        SimpleNamespace(
            sha256="a" * 64
        )
    )

    writer.finalize.return_value = (
        BronzeRunArtifact(
            run_id="run-1",
            run_dir=Path(
                "data/bronze/run-1"
            ),
            manifest_path=Path(
                "data/bronze/run-1/"
                "run_manifest.json"
            ),
            page_count=1,
            record_count=2,
            status="failed",
        )
    )

    with pytest.raises(
        RuntimeError,
        match="before all",
    ):
        ingest_ted_window(
            start_date=date(
                2026,
                9,
                18,
            ),
            end_date=date(
                2026,
                9,
                18,
            ),
            countries=["BEL"],
            client=client,
            writer=writer,
        )

    assert (
        writer.finalize
        .call_args.kwargs[
            "status"
        ]
        == "failed"
    )


def test_ingest_window_rejects_reverse_dates() -> None:
    with pytest.raises(
        ValueError,
        match="end_date",
    ):
        ingest_ted_window(
            start_date=date(
                2026,
                9,
                19,
            ),
            end_date=date(
                2026,
                9,
                18,
            ),
            countries=["BEL"],
        )
