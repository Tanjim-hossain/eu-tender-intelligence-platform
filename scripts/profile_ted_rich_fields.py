from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import TedSearchRequest


QUERY = (
    "publication-date = (20260918 <> 20260924) "
    "AND buyer-country IN (BEL NLD DEU ITA)"
)

FIELDS = [
    "publication-number",
    "publication-date",
    "notice-type",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
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

RICH_FIELDS = [
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

OUTPUT_ROOT = Path(
    "data/bronze/ted/audits"
)


def type_name(value: Any) -> str:
    return type(value).__name__


def main() -> None:
    request = TedSearchRequest(
        query=QUERY,
        fields=FIELDS,
        limit=250,
    )

    client = TedClient()

    type_counts: dict[
        str,
        Counter[str],
    ] = {
        field: Counter()
        for field in RICH_FIELDS
    }

    nested_type_counts: dict[
        str,
        Counter[str],
    ] = {
        field: Counter()
        for field in RICH_FIELDS
    }

    missing_counts: Counter[str] = Counter()

    list_length_min: dict[str, int] = {}
    list_length_max: dict[str, int] = {}

    currencies: Counter[str] = Counter()

    estimated_value_parse_errors = 0

    publication_numbers: set[str] = set()
    duplicate_publication_numbers = 0

    record_count = 0
    page_count = 0
    expected_total: int | None = None

    print("=== TED FULL RICH-FIELD AUDIT ===")

    for page in client.iterate(request):
        page_count += 1

        if expected_total is None:
            expected_total = (
                page.result.parsed
                .total_notice_count
            )

        raw_notices = page.result.raw.get(
            "notices"
        )

        if not isinstance(
            raw_notices,
            list,
        ):
            raise RuntimeError(
                "TED notices payload "
                "must be a list"
            )

        for raw_notice in raw_notices:
            if not isinstance(
                raw_notice,
                dict,
            ):
                raise RuntimeError(
                    "TED notice must be "
                    "a JSON object"
                )

            record_count += 1

            publication_number = (
                raw_notice.get(
                    "publication-number"
                )
            )

            if isinstance(
                publication_number,
                str,
            ):
                if (
                    publication_number
                    in publication_numbers
                ):
                    duplicate_publication_numbers += 1
                else:
                    publication_numbers.add(
                        publication_number
                    )

            for field in RICH_FIELDS:
                value = raw_notice.get(field)

                if value is None:
                    missing_counts[field] += 1
                    continue

                type_counts[field][
                    type_name(value)
                ] += 1

                if isinstance(value, list):
                    length = len(value)

                    list_length_min[field] = min(
                        list_length_min.get(
                            field,
                            length,
                        ),
                        length,
                    )

                    list_length_max[field] = max(
                        list_length_max.get(
                            field,
                            length,
                        ),
                        length,
                    )

                if isinstance(value, dict):
                    for nested_value in (
                        value.values()
                    ):
                        nested_type_counts[
                            field
                        ][
                            type_name(
                                nested_value
                            )
                        ] += 1

            estimated_value = (
                raw_notice.get(
                    "estimated-value-proc"
                )
            )

            if estimated_value is not None:
                try:
                    Decimal(
                        str(estimated_value)
                    )
                except (
                    InvalidOperation,
                    ValueError,
                ):
                    estimated_value_parse_errors += 1

            currency = raw_notice.get(
                "estimated-value-cur-proc"
            )

            if isinstance(currency, str):
                currencies[currency] += 1

        print(
            f"Page {page.page_number:02d}: "
            f"records={record_count}"
        )

    if expected_total is None:
        raise RuntimeError(
            "TED returned no records"
        )

    field_report: dict[
        str,
        dict[str, Any],
    ] = {}

    for field in RICH_FIELDS:
        missing = missing_counts[field]

        field_report[field] = {
            "missing_count": missing,
            "present_count": (
                record_count - missing
            ),
            "coverage_rate": round(
                (
                    record_count - missing
                )
                / record_count,
                6,
            ),
            "top_level_types": dict(
                type_counts[field]
            ),
            "nested_value_types": dict(
                nested_type_counts[field]
            ),
            "list_length_min": (
                list_length_min.get(field)
            ),
            "list_length_max": (
                list_length_max.get(field)
            ),
        }

    report = {
        "query": QUERY,
        "expected_total": expected_total,
        "record_count": record_count,
        "page_count": page_count,
        "unique_publication_numbers": len(
            publication_numbers
        ),
        "duplicate_publication_numbers": (
            duplicate_publication_numbers
        ),
        "estimated_value_parse_errors": (
            estimated_value_parse_errors
        ),
        "currencies": dict(currencies),
        "fields": field_report,
    }

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        UTC
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        OUTPUT_ROOT
        / f"rich_fields_{timestamp}.json"
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )

    print()
    print("=== AUDIT SUMMARY ===")
    print(
        f"Source matches:   {expected_total}"
    )
    print(
        f"Records scanned:  {record_count}"
    )
    print(
        f"Pages:            {page_count}"
    )
    print(
        "Unique notices:   "
        f"{len(publication_numbers)}"
    )
    print(
        "Duplicates:       "
        f"{duplicate_publication_numbers}"
    )
    print(
        "Value parse errors: "
        f"{estimated_value_parse_errors}"
    )

    print()
    print("Field coverage:")

    for field in RICH_FIELDS:
        details = field_report[field]

        print(
            f"  {field}: "
            f"{details['present_count']}/"
            f"{record_count} "
            f"({details['coverage_rate']:.2%}) "
            f"| types="
            f"{details['top_level_types']}"
        )

        if details[
            "nested_value_types"
        ]:
            print(
                "    nested types: "
                f"{details['nested_value_types']}"
            )

        if (
            details["list_length_max"]
            is not None
        ):
            print(
                "    list length: "
                f"{details['list_length_min']}"
                " → "
                f"{details['list_length_max']}"
            )

    print()
    print(
        f"Currencies: {dict(currencies)}"
    )
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()
