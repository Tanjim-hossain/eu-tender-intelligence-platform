from __future__ import annotations

import argparse
from pathlib import Path

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.database.silver_loader import (
    load_silver_tenders,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load TED Silver Parquet into "
            "PostgreSQL."
        )
    )

    parser.add_argument(
        "parquet_path",
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    settings = DatabaseSettings()

    summary = load_silver_tenders(
        args.parquet_path,
        settings,
    )

    print(
        "=== POSTGRES SILVER LOAD ==="
    )
    print(
        f"Parquet rows:  "
        f"{summary.parquet_rows}"
    )
    print(
        f"Inserted rows: "
        f"{summary.inserted_rows}"
    )
    print(
        f"Database rows: "
        f"{summary.database_rows}"
    )
    print("Status:        completed")


if __name__ == "__main__":
    main()
