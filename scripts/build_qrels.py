from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

INPUT_PATH = Path(
    "evaluation/retrieval/"
    "candidates_union_labeled.tsv"
)

OUTPUT_PATH = Path(
    "evaluation/retrieval/qrels.tsv"
)


def main() -> None:
    with INPUT_PATH.open(
        newline=""
    ) as handle:
        rows = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )

    if len(rows) != 288:
        raise RuntimeError(
            "Expected 288 judged query-document pairs, "
            f"found {len(rows)}"
        )

    seen: set[
        tuple[str, str]
    ] = set()

    label_counts: Counter[int] = Counter()
    query_counts: Counter[str] = Counter()

    qrels: list[
        tuple[str, str, int]
    ] = []

    for row in rows:
        query_id = row["query_id"]
        publication_number = (
            row["publication_number"]
        )

        raw_relevance = row[
            "relevance"
        ].strip()

        if raw_relevance == "":
            raise RuntimeError(
                "Found unjudged row: "
                f"{query_id} / "
                f"{publication_number}"
            )

        relevance = int(
            raw_relevance
        )

        if relevance not in {
            0,
            1,
            2,
            3,
        }:
            raise RuntimeError(
                "Invalid relevance grade: "
                f"{relevance}"
            )

        key = (
            query_id,
            publication_number,
        )

        if key in seen:
            raise RuntimeError(
                "Duplicate qrel: "
                f"{query_id} / "
                f"{publication_number}"
            )

        seen.add(key)

        qrels.append(
            (
                query_id,
                publication_number,
                relevance,
            )
        )

        label_counts[
            relevance
        ] += 1

        query_counts[
            query_id
        ] += 1

    if set(query_counts) != {
        f"q{i:02d}"
        for i in range(1, 9)
    }:
        raise RuntimeError(
            "Unexpected query IDs"
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
            lineterminator="\n",
        )

        writer.writerow(
            [
                "query_id",
                "publication_number",
                "relevance",
            ]
        )

        writer.writerows(
            sorted(qrels)
        )

    print(
        "=== FINAL QRELS ==="
    )
    print(
        f"Judgments: {len(qrels)}"
    )
    print(
        "Labels:",
        dict(
            sorted(
                label_counts.items()
            )
        ),
    )
    print(
        "Per query:",
        dict(
            sorted(
                query_counts.items()
            )
        ),
    )
    print(
        f"Output: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
