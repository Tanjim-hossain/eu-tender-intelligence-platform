from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.search.semantic import (
    MODEL_NAME,
    load_semantic_index,
    rank_embeddings,
)

QUERY_PATH = Path(
    "evaluation/retrieval/queries.json"
)

OUTPUT_PATH = Path(
    "evaluation/retrieval/candidates_semantic.tsv"
)

POOL_LIMIT = 20


def main() -> None:
    payload: dict[str, Any] = json.loads(
        QUERY_PATH.read_text()
    )

    queries = payload["queries"]

    publication_numbers, embeddings = (
        load_semantic_index()
    )

    model = SentenceTransformer(
        MODEL_NAME
    )

    query_texts = [
        f"query: {query_spec['text']}"
        for query_spec in queries
    ]

    query_embeddings = model.encode(
        query_texts,
        batch_size=16,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    query_embeddings = np.asarray(
        query_embeddings,
        dtype=np.float32,
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_candidates = 0

    with OUTPUT_PATH.open(
        "w",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writerow(
            [
                "query_id",
                "query",
                "publication_number",
                "semantic_rank",
                "semantic_score",
            ]
        )

        for query_index, query_spec in enumerate(
            queries
        ):
            query_id = query_spec["id"]
            query = query_spec["text"]

            hits = rank_embeddings(
                publication_numbers,
                embeddings,
                query_embeddings[
                    query_index
                ],
                limit=POOL_LIMIT,
            )

            total_candidates += len(
                hits
            )

            print()
            print(
                f"{query_id}: {query}"
            )

            for rank, hit in enumerate(
                hits,
                start=1,
            ):
                writer.writerow(
                    [
                        query_id,
                        query,
                        hit.publication_number,
                        rank,
                        f"{hit.score:.8f}",
                    ]
                )

                if rank <= 5:
                    print(
                        f"  {rank}. "
                        f"{hit.publication_number} "
                        f"| {hit.score:.6f}"
                    )

    print()
    print(
        "=== SEMANTIC RETRIEVAL POOL ==="
    )
    print(
        f"Queries:    {len(queries)}"
    )
    print(
        f"Candidates: {total_candidates}"
    )
    print(
        f"Output:     {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
