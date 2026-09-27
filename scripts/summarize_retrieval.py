"""Print macro averages of the committed historical metrics; no retrieval rerun."""
import csv
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1] / "evaluation" / "retrieval"
METRICS = ("precision_at_10", "recall_at_10", "mrr_at_10", "ndcg_at_10")


def main() -> None:
    print("| System | P@10 | Recall@10 | MRR@10 | nDCG@10 |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for filename, system, label in (
        ("baseline_metrics.tsv", "lexical", "Lexical"),
        ("baseline_metrics.tsv", "semantic", "Semantic"),
        ("hybrid_metrics.tsv", "rrf_broad_weighted", "Weighted hybrid RRF"),
        ("reranker_metrics.tsv", "cross_encoder", "Experimental cross-encoder"),
    ):
        with (ROOT / filename).open(newline="") as handle:
            rows = [row for row in csv.DictReader(handle, delimiter="\t") if row["system"] == system]
        if len(rows) != 8 or len({row["query_id"] for row in rows}) != 8:
            raise ValueError(f"Expected eight unique queries for {system}")
        values = " | ".join(f"{mean(float(row[key]) for row in rows):.4f}" for key in METRICS)
        print(f"| {label} | {values} |")


if __name__ == "__main__":
    main()
