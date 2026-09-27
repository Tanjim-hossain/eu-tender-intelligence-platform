from __future__ import annotations

import statistics
import time

import httpx

URL = "http://127.0.0.1:8000/ask"

CASES = [
    {
        "name": "buyer_deadline",
        "question": (
            "Who is the buyer and what deadline is stated "
            "for the relevant hospital information system tenders?"
        ),
        "query": "hospital information system",
    },
    {
        "name": "comparison",
        "question": (
            "How do the relevant hospital technology "
            "tenders differ?"
        ),
        "query": "hospital information system",
    },
    {
        "name": "sap_context",
        "question": (
            "Why is the Stuttgart hospital information "
            "system tender being procured?"
        ),
        "query": "hospital information system",
    },
    {
        "name": "missing_value",
        "question": (
            "What estimated contract values are stated "
            "for the relevant hospital information system tenders?"
        ),
        "query": "hospital information system",
    },
]


def main() -> None:
    latencies: list[float] = []

    with httpx.Client(
        timeout=180.0
    ) as client:
        for case in CASES:
            started = time.perf_counter()

            response = client.post(
                URL,
                json={
                    "question": case["question"],
                    "query": case["query"],
                    "evidence_limit": 3,
                    "retrieval_depth": 20,
                },
            )

            elapsed_ms = (
                time.perf_counter()
                - started
            ) * 1000.0

            if response.status_code != 200:
                print()
                print("=" * 72)
                print(case["name"])
                print("=" * 72)
                print(
                    f"Latency: {elapsed_ms:.1f} ms"
                )
                print(
                    "HTTP:",
                    response.status_code,
                )
                print(
                    "ERROR:",
                    response.text,
                )
                continue

            payload = response.json()

            latencies.append(elapsed_ms)

            print()
            print("=" * 72)
            print(case["name"])
            print("=" * 72)
            print(
                f"Latency: {elapsed_ms:.1f} ms"
            )
            print(
                "Mode:",
                payload.get("mode"),
            )
            print(
                "Status:",
                payload.get("status"),
            )
            print()
            print(payload.get("answer"))
            print()
            print(
                "Citations:",
                payload.get("citations"),
            )
            print(
                "Sources:",
                [
                    source["publication_number"]
                    for source in payload.get(
                        "sources",
                        [],
                    )
                ],
            )

    print()
    print("=" * 72)
    print("LOCAL RAG LATENCY")
    print("=" * 72)
    if not latencies:
        print("No successful requests; check the API errors above.")
        raise SystemExit(1)
    print(
        f"Mean:   {statistics.mean(latencies):.1f} ms"
    )
    print(
        f"Median: {statistics.median(latencies):.1f} ms"
    )
    print(
        f"Min:    {min(latencies):.1f} ms"
    )
    print(
        f"Max:    {max(latencies):.1f} ms"
    )


if __name__ == "__main__":
    main()
