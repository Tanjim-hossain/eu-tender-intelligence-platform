from __future__ import annotations

from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import TedSearchRequest
from tendergraph.storage.iteration_run import (
    IterationRunWriter,
)

FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "notice-type",
]

QUERY = (
    "publication-date = (20260918 <> 20260924) "
    "AND buyer-country IN (BEL NLD DEU ITA)"
)


def main() -> None:
    request = TedSearchRequest(
        query=QUERY,
        fields=FIELDS,
        limit=250,
    )

    client = TedClient()
    writer = IterationRunWriter()

    total_source_matches: int | None = None
    total_retrieved = 0

    publication_numbers: set[str] = set()
    duplicate_count = 0

    print("=== TED FULL BRONZE INGESTION ===")
    print(f"Run ID: {writer.run_id}")
    print()

    for page in client.iterate(request):
        parsed = page.result.parsed

        if total_source_matches is None:
            total_source_matches = (
                parsed.total_notice_count
            )

        page_count = len(parsed.notices)
        total_retrieved += page_count

        if total_retrieved > total_source_matches:
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

        artifact = writer.write_page(page)

        print(
            f"Page {page.page_number:02d}: "
            f"{page_count:3d} records "
            f"| cumulative={total_retrieved} "
            f"| sha256={artifact.sha256[:12]}..."
        )

    if total_source_matches is None:
        raise RuntimeError(
            "TED returned no iteration pages"
        )

    completed = (
        total_retrieved
        == total_source_matches
    )

    run_artifact = writer.finalize(
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

    print()
    print("=== RUN SUMMARY ===")
    print(
        f"Source matches:    "
        f"{total_source_matches}"
    )
    print(
        f"Records retrieved: "
        f"{total_retrieved}"
    )
    print(
        f"Unique notices:    "
        f"{len(publication_numbers)}"
    )
    print(
        f"Duplicates:        "
        f"{duplicate_count}"
    )
    print(
        f"Pages:             "
        f"{run_artifact.page_count}"
    )
    print(
        f"Status:            "
        f"{run_artifact.status}"
    )
    print(
        f"Manifest:          "
        f"{run_artifact.manifest_path}"
    )

    if not completed:
        raise RuntimeError(
            "TED iteration ended before all "
            "reported records were retrieved"
        )


if __name__ == "__main__":
    main()
