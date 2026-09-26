from __future__ import annotations

import numpy as np
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.semantic import (
    MODEL_NAME,
    load_semantic_index,
    rank_embeddings,
)
from tendergraph.search.vector import (
    search_vector_tenders,
)

QUERIES = [
    "hospital information system",
    "cloud data platform",
    "SAP implementation",
]

K = 10


def main() -> None:
    publication_numbers, embeddings = (
        load_semantic_index()
    )

    model = SentenceTransformer(
        MODEL_NAME
    )

    query_embeddings = model.encode(
        [
            f"query: {query}"
            for query in QUERIES
        ],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    query_embeddings = np.asarray(
        query_embeddings,
        dtype=np.float32,
    )

    settings = DatabaseSettings()

    all_exact = True

    for query, query_vector in zip(
        QUERIES,
        query_embeddings,
        strict=True,
    ):
        local_hits = rank_embeddings(
            publication_numbers,
            embeddings,
            query_vector,
            limit=K,
        )

        database_hits = (
            search_vector_tenders(
                settings,
                query_vector=query_vector,
                model_name=MODEL_NAME,
                limit=K,
            )
        )

        local_ids = [
            hit.publication_number
            for hit in local_hits
        ]

        database_ids = [
            hit.publication_number
            for hit in database_hits
        ]

        exact = (
            local_ids
            == database_ids
        )

        overlap = len(
            set(local_ids)
            & set(database_ids)
        )

        all_exact &= exact

        print()
        print("=" * 80)
        print(query)
        print("=" * 80)
        print(
            f"Exact top-{K}: {exact}"
        )
        print(
            f"Overlap:      "
            f"{overlap}/{K}"
        )

        for rank, (
            local_hit,
            database_hit,
        ) in enumerate(
            zip(
                local_hits,
                database_hits,
                strict=True,
            ),
            start=1,
        ):
            print(
                f"{rank:2d} "
                f"local="
                f"{local_hit.publication_number} "
                f"{local_hit.score:.6f} | "
                f"db="
                f"{database_hit.publication_number} "
                f"{database_hit.score:.6f}"
            )

    print()
    print(
        "=== VECTOR SEARCH PARITY ==="
    )
    print(
        f"All exact: {all_exact}"
    )

    if not all_exact:
        raise SystemExit(
            "Vector ranking parity failed"
        )


if __name__ == "__main__":
    main()
