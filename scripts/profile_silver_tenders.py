from __future__ import annotations

import json
from pathlib import Path

import polars as pl

INPUT = Path(
    "data/silver/ted/tenders.parquet"
)

OUTPUT = Path(
    "data/silver/ted/"
    "tenders_quality_report.json"
)


def main() -> None:
    frame = pl.read_parquet(INPUT)

    row_count = frame.height

    unique_notices = (
        frame["publication_number"].n_unique()
    )

    duplicate_notices = (
        row_count - unique_notices
    )

    null_counts = {
        column: frame[column].null_count()
        for column in frame.columns
    }

    null_rates = {
        column: round(
            null_counts[column] / row_count,
            6,
        )
        for column in frame.columns
    }

    country_counts = (
        frame.select(
            "publication_number",
            "buyer_countries",
        )
        .explode("buyer_countries")
        .group_by("buyer_countries")
        .agg(
            pl.col("publication_number")
            .n_unique()
            .alias("notice_count")
        )
        .sort(
            "notice_count",
            descending=True,
        )
        .to_dicts()
    )

    notice_type_counts = (
        frame.group_by("notice_type")
        .len()
        .sort(
            "len",
            descending=True,
        )
        .to_dicts()
    )

    title_language_counts = (
        frame.group_by("title_language")
        .len()
        .sort(
            "len",
            descending=True,
        )
        .to_dicts()
    )

    cpv_missing = frame[
        "first_cpv_code"
    ].null_count()

    report = {
        "row_count": row_count,
        "column_count": frame.width,
        "unique_publication_numbers": (
            unique_notices
        ),
        "duplicate_publication_numbers": (
            duplicate_notices
        ),
        "publication_date_min": str(
            frame[
                "publication_date"
            ].min()
        ),
        "publication_date_max": str(
            frame[
                "publication_date"
            ].max()
        ),
        "null_counts": null_counts,
        "null_rates": null_rates,
        "primary_cpv_missing": cpv_missing,
        "country_distribution": (
            country_counts
        ),
        "notice_type_distribution": (
            notice_type_counts
        ),
        "title_language_distribution": (
            title_language_counts
        ),
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    print("=== SILVER DATA QUALITY ===")
    print(f"Rows:       {row_count}")
    print(f"Columns:    {frame.width}")
    print(
        f"Unique:     {unique_notices}"
    )
    print(
        f"Duplicates: {duplicate_notices}"
    )

    print()
    print(
        "Publication range: "
        f"{report['publication_date_min']} "
        "→ "
        f"{report['publication_date_max']}"
    )

    print()
    print("Important missing values:")
    for column in [
        "title",
        "buyer_name",
        "first_buyer_country",
        "first_cpv_code",
        "source_html_url",
    ]:
        print(
            f"  {column}: "
            f"{null_counts[column]} "
            f"({null_rates[column]:.2%})"
        )

    print()
    print("Buyer-country memberships:")
    for row in country_counts:
        print(
            f"  {row['buyer_countries']}: "
            f"{row['notice_count']}"
        )

    print()
    print(f"Report: {OUTPUT}")


if __name__ == "__main__":
    main()
