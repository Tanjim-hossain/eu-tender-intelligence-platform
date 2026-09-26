from __future__ import annotations

import statistics
import time

import httpx

URL = "http://127.0.0.1:8000/search"
RUNS = 30

PAYLOAD = {
    "query": "hospital information system",
    "limit": 5,
    "retrieval_depth": 20,
}


def main() -> None:
    latencies_ms: list[float] = []

    with httpx.Client(
        timeout=30.0
    ) as client:
        # Warm-up
        for _ in range(3):
            response = client.post(
                URL,
                json=PAYLOAD,
            )
            response.raise_for_status()

        for _ in range(RUNS):
            started = time.perf_counter()

            response = client.post(
                URL,
                json=PAYLOAD,
            )

            elapsed_ms = (
                time.perf_counter()
                - started
            ) * 1000.0

            response.raise_for_status()

            payload = response.json()

            if (
                payload["results"][0][
                    "publication_number"
                ]
                != "648886-2026"
            ):
                raise RuntimeError(
                    "Unexpected top result"
                )

            latencies_ms.append(
                elapsed_ms
            )

    ordered = sorted(
        latencies_ms
    )

    p95_index = min(
        len(ordered) - 1,
        int(0.95 * len(ordered)),
    )

    print("=== API SEARCH LATENCY ===")
    print(f"Runs:       {RUNS}")
    print(
        "Mean ms:    "
        f"{statistics.mean(latencies_ms):.3f}"
    )
    print(
        "Median ms:  "
        f"{statistics.median(latencies_ms):.3f}"
    )
    print(
        "P95 ms:     "
        f"{ordered[p95_index]:.3f}"
    )
    print(
        "Min ms:     "
        f"{min(latencies_ms):.3f}"
    )
    print(
        "Max ms:     "
        f"{max(latencies_ms):.3f}"
    )


if __name__ == "__main__":
    main()
