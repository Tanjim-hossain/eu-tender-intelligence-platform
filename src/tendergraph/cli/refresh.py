from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from tendergraph.ingestion.window import (
    DEFAULT_COUNTRIES,
    normalize_country_codes,
)
from tendergraph.pipeline.operational import (
    run_operational_refresh,
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
            "Run the incremental TED refresh: "
            "Bronze -> Silver -> PostgreSQL -> "
            "embeddings -> dbt -> audit."
        )
    )

    parser.add_argument(
        "--start-date",
        required=True,
        type=_parse_iso_date,
        metavar="YYYY-MM-DD",
        help=(
            "Inclusive TED publication window start."
        ),
    )

    parser.add_argument(
        "--end-date",
        required=True,
        type=_parse_iso_date,
        metavar="YYYY-MM-DD",
        help=(
            "Inclusive TED publication window end."
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
            "Buyer-country ISO3 codes. "
            "Default: BEL NLD DEU ITA."
        ),
    )

    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=32,
        metavar="N",
        help=(
            "Sentence-transformer encoding batch size "
            "(default: 32)."
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

    if args.embedding_batch_size <= 0:
        parser.error(
            "--embedding-batch-size must be positive"
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
) -> int:
    args = parse_args(
        argv
    )

    print(
        "=== TENDERGRAPH INCREMENTAL REFRESH ==="
    )
    print(
        "Window:       "
        f"{args.start_date.isoformat()} "
        "to "
        f"{args.end_date.isoformat()}"
    )
    print(
        "Countries:    "
        f"{' '.join(args.countries)}"
    )
    print(
        "Embed batch:  "
        f"{args.embedding_batch_size}"
    )
    print()

    summary = run_operational_refresh(
        start_date=args.start_date,
        end_date=args.end_date,
        countries=args.countries,
        embedding_batch_size=(
            args.embedding_batch_size
        ),
    )

    refresh = summary.refresh
    ingestion = refresh.ingestion
    silver = refresh.silver_artifact
    load = refresh.silver_load
    embeddings = refresh.embeddings

    print()
    print(
        "=== REFRESH COMPLETED ==="
    )
    print(
        f"Refresh ID:        "
        f"{summary.refresh_id}"
    )
    print(
        f"Ingestion run ID:  "
        f"{summary.run_id}"
    )
    print(
        f"Bronze retrieved:  "
        f"{ingestion.records_retrieved}"
    )
    print(
        f"Silver rows:       "
        f"{silver.row_count}"
    )
    print(
        f"Inserted rows:     "
        f"{load.inserted_rows}"
    )
    print(
        f"Updated rows:      "
        f"{load.updated_rows}"
    )
    print(
        f"Unchanged rows:    "
        f"{load.unchanged_rows}"
    )
    print(
        f"Changed rows:      "
        f"{refresh.changed_rows}"
    )
    print(
        f"Embedded rows:     "
        f"{embeddings.embedded_rows}"
    )
    print(
        f"Database rows:     "
        f"{load.database_rows}"
    )
    print(
        f"dbt success:       "
        f"{summary.dbt.success}"
    )
    print(
        f"Silver artifact:   "
        f"{silver.parquet_path}"
    )
    print(
        f"Audit record:      "
        f"{summary.audit_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
