from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.evaluation import (
    evaluate_ranking,
)
from tendergraph.search.hybrid import (
    reciprocal_rank_fusion,
)
from tendergraph.search.lexical import (
    ensure_lexical_search,
    search_tenders,
)
from tendergraph.search.pooling import (
    fetch_candidate_pool,
)

QUERY_PATH = Path(
    "evaluation/retrieval/queries.json"
)

QRELS_PATH = Path(
    "evaluation/retrieval/qrels.tsv"
)

SEMANTIC_PATH = Path(
    "evaluation/retrieval/"
    "candidates_semantic.tsv"
)

OUTPUT_PATH = Path(
    "evaluation/retrieval/"
    "hybrid_metrics.tsv"
)

DEPTH = 20
K = 10


def load_qrels() -> dict[
    str,
    dict[str, int],
]:
    qrels: dict[
        str,
        dict[str, int],
    ] = defaultdict(dict)

    with QRELS_PATH.open(
        newline=""
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )

        for row in reader:
            qrels[
                row["query_id"]
            ][
                row["publication_number"]
            ] = int(
                row["relevance"]
            )

    return dict(qrels)


def load_semantic() -> dict[
    str,
    list[str],
]:
    rows: dict[
        str,
        list[tuple[int, str]],
    ] = defaultdict(list)

    with SEMANTIC_PATH.open(
        newline=""
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )

        for row in reader:
            rank = int(
                row["semantic_rank"]
            )

            if rank <= DEPTH:
                rows[
                    row["query_id"]
                ].append(
                    (
                        rank,
                        row[
                            "publication_number"
                        ],
                    )
                )

    return {
        query_id: [
            publication_number
            for _, publication_number
            in sorted(items)
        ]
        for query_id, items
        in rows.items()
    }


def main() -> None:
    payload: dict[str, Any] = json.loads(
        QUERY_PATH.read_text()
    )

    queries = payload["queries"]

    qrels = load_qrels()
    semantic = load_semantic()

    settings = DatabaseSettings()

    ensure_lexical_search(
        settings
    )

    result_rows: list[
        tuple[
            str,
            str,
            str,
            float,
            float,
            float,
            float,
        ]
    ] = []

    for query_spec in queries:
        query_id = query_spec["id"]
        query = query_spec["text"]

        strict_results = search_tenders(
            settings,
            query=query,
            limit=DEPTH,
        )

        strict = [
            result.publication_number
            for result in strict_results
        ]

        broad_results = fetch_candidate_pool(
            settings,
            query=query,
            limit=DEPTH,
        )

        broad = [
            result.publication_number
            for result in broad_results
        ]

        semantic_run = semantic[
            query_id
        ]

        systems = {
            "rrf_strict": (
                reciprocal_rank_fusion(
                    strict,
                    semantic_run,
                    limit=K,
                )
            ),
            "rrf_broad": (
                reciprocal_rank_fusion(
                    broad,
                    semantic_run,
                    limit=K,
                )
            ),
        }

        for system, hits in systems.items():
            retrieved = [
                hit.publication_number
                for hit in hits
            ]

            metrics = evaluate_ranking(
                retrieved,
                qrels[query_id],
                k=K,
                minimum_relevance=2,
            )

            result_rows.append(
                (
                    query_id,
                    query,
                    system,
                    metrics.precision_at_k,
                    metrics.recall_at_k,
                    metrics.reciprocal_rank,
                    metrics.ndcg_at_k,
                )
            )

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
                "system",
                "precision_at_10",
                "recall_at_10",
                "mrr_at_10",
                "ndcg_at_10",
            ]
        )

        writer.writerows(
            (
                query_id,
                query,
                system,
                f"{precision:.6f}",
                f"{recall:.6f}",
                f"{mrr:.6f}",
                f"{ndcg:.6f}",
            )
            for (
                query_id,
                query,
                system,
                precision,
                recall,
                mrr,
                ndcg,
            ) in result_rows
        )

    print("=== HYBRID RETRIEVAL ===")
    print("RRF depth: 20")
    print("RRF k:     60")

    for system in (
        "rrf_strict",
        "rrf_broad",
    ):
        rows = [
            row
            for row in result_rows
            if row[2] == system
        ]

        print()
        print(system.upper())

        print(
            "Precision@10:",
            f"{mean(
                row[3]
                for row in rows
            ):.4f}",
        )

        print(
            "Recall@10:   ",
            f"{mean(
                row[4]
                for row in rows
            ):.4f}",
        )

        print(
            "MRR@10:      ",
            f"{mean(
                row[5]
                for row in rows
            ):.4f}",
        )

        print(
            "nDCG@10:     ",
            f"{mean(
                row[6]
                for row in rows
            ):.4f}",
        )

    print()

    for row in result_rows:
        print(
            f"{row[0]} "
            f"{row[2]:10s} "
            f"P={row[3]:.3f} "
            f"R={row[4]:.3f} "
            f"MRR={row[5]:.3f} "
            f"nDCG={row[6]:.3f}"
        )

    print()
    print(
        f"Output: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
