from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import polars as pl

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.evaluation import (
    evaluate_ranking,
)
from tendergraph.search.hybrid import (
    reciprocal_rank_fusion,
)
from tendergraph.search.pooling import (
    fetch_candidate_pool,
)
from tendergraph.search.reranker import (
    CrossEncoderReranker,
    reranker_document_text,
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

SILVER_PATH = Path(
    "data/silver/ted/tenders.parquet"
)

OUTPUT_PATH = Path(
    "evaluation/retrieval/"
    "reranker_metrics.tsv"
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


def load_documents() -> dict[str, str]:
    frame = pl.read_parquet(
        SILVER_PATH
    )

    return {
        str(row["publication_number"]):
            reranker_document_text(row)
        for row in frame.iter_rows(
            named=True
        )
    }


def main() -> None:
    payload: dict[str, Any] = (
        json.loads(
            QUERY_PATH.read_text()
        )
    )

    queries = payload["queries"]
    qrels = load_qrels()
    semantic = load_semantic()
    documents = load_documents()

    settings = DatabaseSettings()

    reranker = CrossEncoderReranker()

    print(
        "=== CROSS-ENCODER RERANKER ==="
    )
    print(
        f"Model:  {reranker.model_name}"
    )
    print(
        f"Device: {reranker.device}"
    )
    print(
        f"Depth:  {DEPTH}"
    )
    print(
        f"K:      {K}"
    )

    rows: list[
        tuple[
            str,
            str,
            str,
            float,
            float,
            float,
            float,
            float,
        ]
    ] = []

    total_rerank_ms = 0.0

    for query_spec in queries:
        query_id = query_spec["id"]
        query = query_spec["text"]

        broad_results = (
            fetch_candidate_pool(
                settings,
                query=query,
                limit=DEPTH,
            )
        )

        broad = [
            result.publication_number
            for result in broad_results
        ]

        weighted_hits = (
            reciprocal_rank_fusion(
                broad,
                semantic[query_id],
                limit=DEPTH,
                lexical_weight=1.0,
                semantic_weight=1.25,
            )
        )

        candidates = [
            hit.publication_number
            for hit in weighted_hits
        ]

        baseline = candidates[:K]

        baseline_metrics = (
            evaluate_ranking(
                baseline,
                qrels[query_id],
                k=K,
                minimum_relevance=2,
            )
        )

        started = time.perf_counter()

        reranked_hits = reranker.rerank(
            query,
            candidates,
            documents,
            limit=K,
            batch_size=16,
        )

        rerank_ms = (
            time.perf_counter()
            - started
        ) * 1000.0

        total_rerank_ms += rerank_ms

        reranked = [
            hit.publication_number
            for hit in reranked_hits
        ]

        reranked_metrics = (
            evaluate_ranking(
                reranked,
                qrels[query_id],
                k=K,
                minimum_relevance=2,
            )
        )

        for system, metrics in (
            (
                "weighted_rrf",
                baseline_metrics,
            ),
            (
                "cross_encoder",
                reranked_metrics,
            ),
        ):
            rows.append(
                (
                    query_id,
                    query,
                    system,
                    metrics.precision_at_k,
                    metrics.recall_at_k,
                    metrics.reciprocal_rank,
                    metrics.ndcg_at_k,
                    (
                        0.0
                        if system
                        == "weighted_rrf"
                        else rerank_ms
                    ),
                )
            )

        print()
        print(
            f"{query_id} {query}"
        )
        print(
            f"Rerank latency: "
            f"{rerank_ms:.1f} ms"
        )
        print(
            "Top 3:",
            ", ".join(
                hit.publication_number
                for hit
                in reranked_hits[:3]
            ),
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
                "rerank_latency_ms",
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
                f"{latency:.3f}",
            )
            for (
                query_id,
                query,
                system,
                precision,
                recall,
                mrr,
                ndcg,
                latency,
            ) in rows
        )

    print()
    print(
        "=== AGGREGATE METRICS ==="
    )

    for system in (
        "weighted_rrf",
        "cross_encoder",
    ):
        system_rows = [
            row
            for row in rows
            if row[2] == system
        ]

        print()
        print(system.upper())

        print(
            "Precision@10:",
            f"{mean(
                row[3]
                for row in system_rows
            ):.4f}",
        )
        print(
            "Recall@10:   ",
            f"{mean(
                row[4]
                for row in system_rows
            ):.4f}",
        )
        print(
            "MRR@10:      ",
            f"{mean(
                row[5]
                for row in system_rows
            ):.4f}",
        )
        print(
            "nDCG@10:     ",
            f"{mean(
                row[6]
                for row in system_rows
            ):.4f}",
        )

    print()
    print(
        "Mean rerank latency:",
        f"{total_rerank_ms / len(queries):.1f} ms",
    )
    print(
        f"Output: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
