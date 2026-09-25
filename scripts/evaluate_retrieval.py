from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.evaluation import (
    RetrievalMetrics,
    evaluate_ranking,
)
from tendergraph.search.lexical import (
    ensure_lexical_search,
    search_tenders,
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
    "baseline_metrics.tsv"
)

K = 10
MINIMUM_RELEVANCE = 2


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    query_id: str
    query: str
    system: str
    retrieved: int
    precision_at_10: float
    recall_at_10: float
    mrr_at_10: float
    ndcg_at_10: float


def read_qrels() -> dict[
    str,
    dict[str, int],
]:
    result: dict[
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
            result[
                row["query_id"]
            ][
                row[
                    "publication_number"
                ]
            ] = int(
                row["relevance"]
            )

    return dict(result)


def read_semantic_run() -> dict[
    str,
    list[str],
]:
    result: dict[
        str,
        list[
            tuple[int, str]
        ],
    ] = defaultdict(list)

    with SEMANTIC_PATH.open(
        newline=""
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )

        for row in reader:
            result[
                row["query_id"]
            ].append(
                (
                    int(
                        row[
                            "semantic_rank"
                        ]
                    ),
                    row[
                        "publication_number"
                    ],
                )
            )

    return {
        query_id: [
            publication_number
            for rank, publication_number
            in sorted(rows)
            if rank <= K
        ]
        for query_id, rows
        in result.items()
    }


def evaluate_one(
    *,
    query_id: str,
    query: str,
    system: str,
    retrieved: list[str],
    relevance: dict[str, int],
) -> EvaluationRow:
    metrics: RetrievalMetrics = (
        evaluate_ranking(
            retrieved,
            relevance,
            k=K,
            minimum_relevance=(
                MINIMUM_RELEVANCE
            ),
        )
    )

    return EvaluationRow(
        query_id=query_id,
        query=query,
        system=system,
        retrieved=len(
            retrieved[:K]
        ),
        precision_at_10=(
            metrics.precision_at_k
        ),
        recall_at_10=(
            metrics.recall_at_k
        ),
        mrr_at_10=(
            metrics.reciprocal_rank
        ),
        ndcg_at_10=(
            metrics.ndcg_at_k
        ),
    )


def main() -> None:
    payload: dict[str, Any] = (
        json.loads(
            QUERY_PATH.read_text()
        )
    )

    queries = payload["queries"]

    qrels = read_qrels()

    semantic_run = (
        read_semantic_run()
    )

    settings = DatabaseSettings()

    ensure_lexical_search(
        settings
    )

    rows: list[
        EvaluationRow
    ] = []

    for query_spec in queries:
        query_id = query_spec["id"]
        query = query_spec["text"]

        lexical_results = (
            search_tenders(
                settings,
                query=query,
                limit=K,
            )
        )

        lexical_run = [
            result.publication_number
            for result
            in lexical_results
        ]

        rows.append(
            evaluate_one(
                query_id=query_id,
                query=query,
                system="lexical",
                retrieved=lexical_run,
                relevance=qrels[
                    query_id
                ],
            )
        )

        rows.append(
            evaluate_one(
                query_id=query_id,
                query=query,
                system="semantic",
                retrieved=semantic_run[
                    query_id
                ],
                relevance=qrels[
                    query_id
                ],
            )
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            delimiter="\t",
        )

        writer.writerow(
            [
                "query_id",
                "query",
                "system",
                "retrieved_at_10",
                "precision_at_10",
                "recall_at_10",
                "mrr_at_10",
                "ndcg_at_10",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.query_id,
                    row.query,
                    row.system,
                    row.retrieved,
                    (
                        f"{row.precision_at_10:.6f}"
                    ),
                    (
                        f"{row.recall_at_10:.6f}"
                    ),
                    (
                        f"{row.mrr_at_10:.6f}"
                    ),
                    (
                        f"{row.ndcg_at_10:.6f}"
                    ),
                ]
            )

    print(
        "=== RETRIEVAL BASELINE ==="
    )
    print(
        "Binary relevance: grade >= 2"
    )
    print(
        "nDCG relevance: grades 0-3"
    )
    print(
        "Recall is pooled recall over "
        "the judged union."
    )

    for system in (
        "lexical",
        "semantic",
    ):
        system_rows = [
            row
            for row in rows
            if row.system == system
        ]

        print()
        print(
            system.upper()
        )
        print(
            "Precision@10:",
            f"{mean(
                row.precision_at_10
                for row in system_rows
            ):.4f}",
        )
        print(
            "Recall@10:   ",
            f"{mean(
                row.recall_at_10
                for row in system_rows
            ):.4f}",
        )
        print(
            "MRR@10:      ",
            f"{mean(
                row.mrr_at_10
                for row in system_rows
            ):.4f}",
        )
        print(
            "nDCG@10:     ",
            f"{mean(
                row.ndcg_at_10
                for row in system_rows
            ):.4f}",
        )

    print()
    print(
        "Per-query results:"
    )

    for row in rows:
        print(
            f"{row.query_id} "
            f"{row.system:8s} "
            f"P={row.precision_at_10:.3f} "
            f"R={row.recall_at_10:.3f} "
            f"MRR={row.mrr_at_10:.3f} "
            f"nDCG={row.ndcg_at_10:.3f}"
        )

    print()
    print(
        f"Output: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
