import json
from datetime import UTC, datetime
from pathlib import Path

from tendergraph.ingestion.client import (
    TedIterationPage,
    TedSearchResult,
)
from tendergraph.ingestion.models import (
    TedSearchRequest,
    TedSearchResponse,
)
from tendergraph.storage.iteration_run import (
    IterationRunWriter,
)


def make_page(
    *,
    page_number: int,
    publication_number: str,
    next_token: str | None,
) -> TedIterationPage:
    raw = {
        "notices": [
            {
                "notice-type": "cn-standard",
                "publication-number": (
                    publication_number
                ),
                "publication-date": (
                    "2026-09-24+02:00"
                ),
                "classification-cpv": [
                    "72000000"
                ],
                "buyer-name": {
                    "eng": ["Example Authority"]
                },
                "buyer-country": ["BEL"],
                "notice-title": {
                    "eng": "Example tender"
                },
                "links": {},
            }
        ],
        "totalNoticeCount": 2,
        "iterationNextToken": next_token,
        "timedOut": False,
    }

    request = TedSearchRequest(
        query="buyer-country = BEL",
        fields=["publication-number"],
        limit=250,
        pagination_mode="ITERATION",
        iteration_next_token=(
            None
            if page_number == 1
            else "token-page-2"
        ),
    )

    return TedIterationPage(
        page_number=page_number,
        request=request,
        result=TedSearchResult(
            raw=raw,
            parsed=(
                TedSearchResponse.model_validate(
                    raw
                )
            ),
        ),
    )


def test_iteration_run_writer_creates_summary(
    tmp_path: Path,
) -> None:
    started_at = datetime(
        2026,
        9,
        24,
        20,
        0,
        tzinfo=UTC,
    )

    writer = IterationRunWriter(
        root=tmp_path / "runs",
        started_at=started_at,
    )

    writer.write_page(
        make_page(
            page_number=1,
            publication_number="100001-2026",
            next_token="token-page-2",
        ),
        retrieved_at=started_at,
    )

    writer.write_page(
        make_page(
            page_number=2,
            publication_number="100002-2026",
            next_token=None,
        ),
        retrieved_at=datetime(
            2026,
            9,
            24,
            20,
            1,
            tzinfo=UTC,
        ),
    )

    request = TedSearchRequest(
        query="buyer-country = BEL",
        fields=["publication-number"],
        limit=250,
    )

    artifact = writer.finalize(
        request=request,
        total_source_matches=2,
        unique_publication_numbers=2,
        duplicate_publication_numbers=0,
        status="completed",
        finished_at=datetime(
            2026,
            9,
            24,
            20,
            2,
            tzinfo=UTC,
        ),
    )

    assert artifact.page_count == 2
    assert artifact.record_count == 2

    manifest = json.loads(
        artifact.manifest_path.read_text()
    )

    assert manifest["status"] == "completed"
    assert manifest["record_count"] == 2
    assert manifest["page_count"] == 2
    assert manifest["complete_count_match"] is True
    assert len(manifest["pages"]) == 2
