from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import (
    TedSearchRequest,
)
from tendergraph.ingestion.window import (
    DEFAULT_COUNTRIES,
    build_publication_window_query,
    normalize_country_codes,
)
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

DEFAULT_START_DATE = date(
    2026,
    9,
    18,
)

DEFAULT_END_DATE = date(
    2026,
    9,
    24,
)


def _parse_iso_date(
    value: str,
) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Expected date in YYYY-MM-DD format"
        ) from exc


def _parse_country(
    value: str,
) -> str:
    try:
        return normalize_country_codes(
            [value]
        )[0]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            str(exc)
        ) from exc


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest a TED publication-date window "
            "into immutable Bronze storage."
        )
    )

    parser.add_argument(
        "--start-date",
        type=_parse_iso_date,
        default=DEFAULT_START_DATE,
        metavar="YYYY-MM-DD",
        help=(
            "Inclusive publication window start "
            "(default: 2026-09-18)."
        ),
    )

    parser.add_argument(
        "--end-date",
        type=_parse_iso_date,
        default=DEFAULT_END_DATE,
        metavar="YYYY-MM-DD",
        help=(
            "Inclusive publication window end "
            "(default: 2026-09-24)."
        ),
    )

    parser.add_argument(
        "--countries",
        nargs="+",
        type=_parse_country,
        default=list(DEFAULT_COUNTRIES),
        metavar="ISO3",
        help=(
            "Buyer-country ISO3 codes separated "
            "by spaces."
        ),
    )

    args = parser.parse_args(argv)

    if args.end_date < args.start_date:
        parser.error(
            "--end-date must be on or after "
            "--start-date"
        )

    try:
        normalize_country_codes(
            args.countries
        )
    except ValueError as exc:
        parser.error(str(exc))

    return args


def main(
    argv: Sequence[str] | None = None,
) -> None:
    args = parse_args(argv)

    query = build_publication_window_query(
        start_date=args.start_date,
        end_date=args.end_date,
        countries=args.countries,
    )

    request = TedSearchRequest(
        query=query,
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
    print(
        "Window: "
        f"{args.start_date.isoformat()} "
        "to "
        f"{args.end_date.isoformat()}"
    )
    print(
        "Countries: "
        f"{' '.join(args.countries)}"
    )
    print(f"Query: {query}")
    print()

    for page in client.iterate(request):
        parsed = page.result.parsed

        if total_source_matches is None:
            total_source_matches = (
                parsed.total_notice_count
            )

        page_count = len(parsed.notices)
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
        "Source matches:    "
        f"{total_source_matches}"
    )
    print(
        "Records retrieved: "
        f"{total_retrieved}"
    )
    print(
        "Unique notices:    "
        f"{len(publication_numbers)}"
    )
    print(
        "Duplicates:        "
        f"{duplicate_count}"
    )
    print(
        "Pages:             "
        f"{run_artifact.page_count}"
    )
    print(
        "Status:            "
        f"{run_artifact.status}"
    )
    print(
        "Manifest:          "
        f"{run_artifact.manifest_path}"
    )

    if not completed:
        raise RuntimeError(
            "TED iteration ended before all "
            "reported records were retrieved"
        )


if __name__ == "__main__":
    main()
