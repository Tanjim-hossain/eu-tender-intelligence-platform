from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from tendergraph.ingestion.client import (
    TedIterationPage,
)
from tendergraph.ingestion.runner import (
    ingest_ted_window,
)
from tendergraph.ingestion.window import (
    DEFAULT_COUNTRIES,
    normalize_country_codes,
)
from tendergraph.storage.bronze import BronzeArtifact

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
        return date.fromisoformat(
            value
        )
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
        default=list(
            DEFAULT_COUNTRIES
        ),
        metavar="ISO3",
        help=(
            "Buyer-country ISO3 codes separated "
            "by spaces."
        ),
    )

    args = parser.parse_args(
        argv
    )

    if (
        args.end_date
        < args.start_date
    ):
        parser.error(
            "--end-date must be on or after "
            "--start-date"
        )

    try:
        normalize_country_codes(
            args.countries
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    return args


def _print_page(
    page: TedIterationPage,
    artifact: BronzeArtifact,
    total_retrieved: int,
) -> None:
    page_count = len(
        page.result.parsed.notices
    )

    print(
        f"Page {page.page_number:02d}: "
        f"{page_count:3d} records "
        f"| cumulative={total_retrieved} "
        f"| sha256={artifact.sha256[:12]}..."
    )


def main(
    argv: Sequence[str] | None = None,
) -> None:
    args = parse_args(
        argv
    )

    print(
        "=== TED FULL BRONZE INGESTION ==="
    )
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
    print()

    result = ingest_ted_window(
        start_date=args.start_date,
        end_date=args.end_date,
        countries=args.countries,
        on_page=_print_page,
    )

    print()
    print(
        "=== RUN SUMMARY ==="
    )
    print(
        f"Run ID:            "
        f"{result.run_artifact.run_id}"
    )
    print(
        f"Query:             "
        f"{result.query}"
    )
    print(
        f"Source matches:    "
        f"{result.total_source_matches}"
    )
    print(
        f"Records retrieved: "
        f"{result.records_retrieved}"
    )
    print(
        f"Unique notices:    "
        f"{result.unique_publication_numbers}"
    )
    print(
        f"Duplicates:        "
        f"{result.duplicate_publication_numbers}"
    )
    print(
        f"Pages:             "
        f"{result.run_artifact.page_count}"
    )
    print(
        f"Status:            "
        f"{result.run_artifact.status}"
    )
    print(
        f"Run directory:     "
        f"{result.run_artifact.run_dir}"
    )
    print(
        f"Manifest:          "
        f"{result.run_artifact.manifest_path}"
    )


if __name__ == "__main__":
    main()
