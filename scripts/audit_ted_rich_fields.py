from __future__ import annotations

import json
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


def describe_value(value: Any) -> str:
    if value is None:
        return "None"

    rendered = json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )

    if len(rendered) > 500:
        rendered = rendered[:500] + "..."

    return (
        f"type={type(value).__name__} "
        f"value={rendered}"
    )


def main() -> None:
    request = TedSearchRequest(
        query=QUERY,
        fields=FIELDS,
        limit=5,
    )

    result = TedClient().search(request)

    print("=== TED RICH FIELD AUDIT ===")
    print(
        "Total source matches:",
        result.parsed.total_notice_count,
    )
    print(
        "Downloaded:",
        len(result.parsed.notices),
    )

    for index, raw_notice in enumerate(
        result.raw["notices"],
        start=1,
    ):
        print()
        print("=" * 80)
        print(
            f"NOTICE {index}: "
            f"{raw_notice.get('publication-number')}"
        )
        print("=" * 80)

        for field in FIELDS:
            print(
                f"{field}: "
                f"{describe_value(raw_notice.get(field))}"
            )


if __name__ == "__main__":
    main()
