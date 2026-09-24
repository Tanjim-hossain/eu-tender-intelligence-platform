from __future__ import annotations

import argparse
from pathlib import Path

from tendergraph.processing.silver import (
    build_silver_dataframe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build normalized TED Silver Parquet "
            "from one completed Bronze run."
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

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.write_parquet(
        args.output,
        compression="zstd",
    )

    print("=== TED SILVER BUILD ===")
    print(
        f"Rows:             {frame.height}"
    )
    print(
        f"Columns:          {frame.width}"
    )
    print(
        "Unique notices:   "
        f"{frame['publication_number'].n_unique()}"
    )

    print()
    print("Null counts:")

    for column in [
        "title",
        "buyer_name",
        "first_buyer_country",
        "first_cpv_code",
        "source_html_url",
    ]:
        print(
            f"  {column}: "
            f"{frame[column].null_count()}"
        )

    print()
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
