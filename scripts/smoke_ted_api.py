from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

QUERY = (
    "publication-date = (20260918 <> 20260924) "
    "AND buyer-country IN (BEL NLD DEU ITA)"
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

PAYLOAD: dict[str, Any] = {
    "query": QUERY,
    "fields": FIELDS,
    "page": 1,
    "limit": 20,
    "scope": "ALL",
    "checkQuerySyntax": False,
    "paginationMode": "PAGE_NUMBER",
    "onlyLatestVersions": True,
}


def main() -> None:
    print("=== TED Search API Smoke Test ===")
    print(f"Endpoint: {TED_SEARCH_URL}")
    print(f"Query:    {QUERY}")
    print()

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            TED_SEARCH_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=PAYLOAD,
        )

    print(f"HTTP status: {response.status_code}")

    if response.status_code != 200:
        print("\n=== TED API ERROR ===")
        print(response.text)
        response.raise_for_status()

    body = response.json()

    notices = body.get("notices", [])
    total_count = body.get("totalNoticeCount")
    timed_out = body.get("timedOut")

    print(f"Total matching notices: {total_count}")
    print(f"Downloaded notices:     {len(notices)}")
    print(f"Timed out:              {timed_out}")
    print(f"Response fields:        {list(body.keys())}")

    if notices:
        first_notice = notices[0]

        print("\n=== FIRST NOTICE FIELD TYPES ===")
        for key, value in first_notice.items():
            print(f"{key}: {type(value).__name__}")

        print("\n=== FIRST NOTICE ===")
        print(
            json.dumps(
                first_notice,
                indent=2,
                ensure_ascii=False,
            )
        )

    timestamp = datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_dir = Path("data/bronze/ted/smoke")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = (
        output_dir / f"ted_search_{timestamp}.json"
    )

    artifact = {
        "metadata": {
            "source": "TED Search API v3",
            "endpoint": TED_SEARCH_URL,
            "retrieved_at_utc": timestamp,
            "query": QUERY,
            "requested_fields": FIELDS,
            "scope": PAYLOAD["scope"],
            "pagination_mode": PAYLOAD["paginationMode"],
            "only_latest_versions": PAYLOAD[
                "onlyLatestVersions"
            ],
        },
        "request": PAYLOAD,
        "response": body,
    }

    output_path.write_text(
        json.dumps(
            artifact,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n=== BRONZE ARTIFACT ===")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
