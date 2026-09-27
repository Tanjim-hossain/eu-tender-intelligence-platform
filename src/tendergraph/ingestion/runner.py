from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from tendergraph.ingestion.client import (
    TedClient,
    TedIterationPage,
)
from tendergraph.ingestion.models import (
    TedSearchRequest,
)
from tendergraph.ingestion.window import (
    build_publication_window_query,
    normalize_country_codes,
)
from tendergraph.storage.bronze import BronzeArtifact
from tendergraph.storage.iteration_run import (
    BronzeRunArtifact,
    IterationRunWriter,
)

TED_FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "notice-type",
    "description-proc",
    "description-lot",
    "procedure-type",
    "contract-nature",
    "deadline",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "place-of-performance-country-proc",
    "place-of-performance-subdiv-proc",
]


@dataclass(frozen=True, slots=True)
class TedIngestionResult:
    run_artifact: BronzeRunArtifact
    query: str
    total_source_matches: int
    records_retrieved: int
    unique_publication_numbers: int
    duplicate_publication_numbers: int


PageCallback = Callable[
    [
        TedIterationPage,
        BronzeArtifact,
        int,
    ],
    None,
]


def ingest_ted_window(
    *,
    start_date: date,
    end_date: date,
    countries: Sequence[str],
    client: TedClient | None = None,
    writer: IterationRunWriter | None = None,
    on_page: PageCallback | None = None,
) -> TedIngestionResult:
    """Ingest one TED publication window into immutable Bronze."""

    if end_date < start_date:
        raise ValueError(
            "end_date must be on or after start_date"
        )

    normalized_countries = (
        normalize_country_codes(
            countries
        )
    )

    query = build_publication_window_query(
        start_date=start_date,
        end_date=end_date,
        countries=normalized_countries,
    )

    request = TedSearchRequest(
        query=query,
        fields=TED_FIELDS,
        limit=250,
    )

    active_client = (
        client
        if client is not None
        else TedClient()
    )

    active_writer = (
        writer
        if writer is not None
        else IterationRunWriter()
    )

    total_source_matches: int | None = None
    total_retrieved = 0

    publication_numbers: set[str] = set()
    duplicate_count = 0

    for page in active_client.iterate(
        request
    ):
        parsed = page.result.parsed

        if total_source_matches is None:
            total_source_matches = (
                parsed.total_notice_count
            )

        page_count = len(
            parsed.notices
        )

        total_retrieved += page_count

        if (
            total_source_matches is not None
            and total_retrieved
            > total_source_matches
        ):
            raise RuntimeError(
                "Retrieved more TED records than "
                "totalNoticeCount: "
                f"{total_retrieved}/"
                f"{total_source_matches}"
            )

        for notice in parsed.notices:
            publication_number = (
                notice.publication_number
            )

            if (
                publication_number
                in publication_numbers
            ):
                duplicate_count += 1
            else:
                publication_numbers.add(
                    publication_number
                )

        artifact = (
            active_writer.write_page(
                page
            )
        )

        if on_page is not None:
            on_page(
                page,
                artifact,
                total_retrieved,
            )

    if total_source_matches is None:
        raise RuntimeError(
            "TED returned no iteration pages"
        )

    completed = (
        total_retrieved
        == total_source_matches
    )

    run_artifact = (
        active_writer.finalize(
            request=request,
            total_source_matches=(
                total_source_matches
            ),
            unique_publication_numbers=len(
                publication_numbers
            ),
            duplicate_publication_numbers=(
                duplicate_count
            ),
            status=(
                "completed"
                if completed
                else "failed"
            ),
        )
    )

    if not completed:
        raise RuntimeError(
            "TED iteration ended before all "
            "reported records were retrieved"
        )

    return TedIngestionResult(
        run_artifact=run_artifact,
        query=query,
        total_source_matches=(
            total_source_matches
        ),
        records_retrieved=total_retrieved,
        unique_publication_numbers=len(
            publication_numbers
        ),
        duplicate_publication_numbers=(
            duplicate_count
        ),
    )
