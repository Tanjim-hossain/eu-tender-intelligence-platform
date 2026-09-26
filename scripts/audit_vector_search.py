from __future__ import annotations

import statistics
import time

import numpy as np
import psycopg
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.semantic import (
    MODEL_NAME,
)
from tendergraph.search.vector import (
    search_vector_tenders,
    vector_literal,
)

QUERY = "hospital information system"
RUNS = 30
LIMIT = 10


def main() -> None:
    model = SentenceTransformer(
        MODEL_NAME
    )

    query_vector = model.encode(
        [f"query: {QUERY}"],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]

    query_vector = np.asarray(
        query_vector,
        dtype=np.float32,
    )

    settings = DatabaseSettings()

    # Warm-up
    for _ in range(3):
        search_vector_tenders(
            settings,
            query_vector=query_vector,
            model_name=MODEL_NAME,
            limit=LIMIT,
        )

    latencies_ms: list[float] = []

    for _ in range(RUNS):
        start = time.perf_counter()

        results = search_vector_tenders(
            settings,
            query_vector=query_vector,
            model_name=MODEL_NAME,
            limit=LIMIT,
        )

        elapsed_ms = (
            time.perf_counter()
            - start
        ) * 1000.0

        latencies_ms.append(
            elapsed_ms
        )

    sorted_latencies = sorted(
        latencies_ms
    )

    p95_index = min(
        len(sorted_latencies) - 1,
        int(
            0.95
            * len(sorted_latencies)
        ),
    )

    print(
        "=== VECTOR SEARCH LATENCY ==="
    )
    print(f"Query: {QUERY}")
    print(f"Runs:  {RUNS}")
    print(
        "Top result:",
        results[0].publication_number,
    )
    print(
        "Mean ms:",
        f"{statistics.mean(latencies_ms):.3f}",
    )
    print(
        "Median ms:",
        f"{statistics.median(latencies_ms):.3f}",
    )
    print(
        "P95 ms:",
        f"{sorted_latencies[p95_index]:.3f}",
    )
    print(
        "Min ms:",
        f"{min(latencies_ms):.3f}",
    )
    print(
        "Max ms:",
        f"{max(latencies_ms):.3f}",
    )

    literal = vector_literal(
        query_vector
    )

    explain_sql = """
    EXPLAIN (
        ANALYZE,
        BUFFERS,
        VERBOSE,
        FORMAT TEXT
    )
    SELECT
        e.publication_number,
        e.embedding <=> %(vector)s::vector
            AS distance
    FROM search.tender_embeddings AS e
    WHERE
        e.model_name = %(model_name)s
    ORDER BY
        e.embedding <=> %(vector)s::vector
    LIMIT %(limit)s;
    """

    with psycopg.connect(
        settings.connection_uri
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            explain_sql,
            {
                "vector": literal,
                "model_name": MODEL_NAME,
                "limit": LIMIT,
            },
        )

        plan = cursor.fetchall()

    print()
    print(
        "=== POSTGRESQL QUERY PLAN ==="
    )

    for row in plan:
        print(row[0])


if __name__ == "__main__":
    main()
