from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from tendergraph.processing.quality import (
    validate_silver_tenders,
)
from tendergraph.processing.silver import (
    build_silver_dataframe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate normalized TED "
            "Silver Parquet from one completed "
            "Bronze run."
        )
    )

    parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to completed Bronze run directory",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/silver/ted/tenders.parquet"
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    frame = build_silver_dataframe(
        args.run_dir
    )

    summary = validate_silver_tenders(
        frame
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_output = (
        args.output.parent
        / f".{args.output.name}.tmp"
    )

    temporary_output.unlink(
        missing_ok=True
    )

    try:
        frame.write_parquet(
            temporary_output,
            compression="zstd",
        )

        persisted = pl.read_parquet(
            temporary_output
        )

        persisted_summary = (
            validate_silver_tenders(
                persisted
            )
        )

        if persisted.schema != frame.schema:
            raise ValueError(
                "Persisted Silver schema does "
                "not match in-memory schema"
            )

        if (
            persisted_summary.row_count
            != summary.row_count
        ):
            raise ValueError(
                "Persisted Silver row count "
                "does not match source build"
            )

        temporary_output.replace(
            args.output
        )

    except Exception:
        temporary_output.unlink(
            missing_ok=True
        )
        raise

    print("=== TED SILVER V2 BUILD ===")

    print(
        f"Rows:              "
        f"{summary.row_count}"
    )

    print(
        f"Columns:           "
        f"{frame.width}"
    )

    print(
        "Unique notices:    "
        f"{summary.unique_publication_numbers}"
    )

    print(
        "Duplicates:        "
        f"{summary.duplicate_publication_numbers}"
    )

    print(
        "Out-of-scope rows: "
        f"{summary.out_of_scope_rows}"
    )

    print(
        "Rows w/ deadlines: "
        f"{summary.rows_with_deadlines}"
    )

    print(
        "Rows w/ value:     "
        f"{summary.rows_with_estimated_value}"
    )

    print()
    print("Rich-field coverage:")

    for column in [
        "description",
        "procedure_type",
        "earliest_deadline",
        "estimated_value",
        "performance_countries",
        "performance_regions",
    ]:
        if (
            frame.schema[column]
            == pl.List(pl.String)
        ):
            count = frame.filter(
                pl.col(column)
                .list.len()
                .fill_null(0)
                > 0
            ).height
        else:
            count = frame.filter(
                pl.col(column).is_not_null()
            ).height

        percentage = (
            100 * count / frame.height
        )

        print(
            f"  {column:24} "
            f"{count:4}/{frame.height} "
            f"({percentage:6.2f}%)"
        )

    print()
    print(
        f"Output: {args.output}"
    )


if __name__ == "__main__":
    main()
