from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

QUERY_PATH = Path(
    "evaluation/retrieval/queries.json"
)

LEXICAL_PATH = Path(
    "evaluation/retrieval/"
    "candidates_lexical_labeled.tsv"
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
    "candidates_union.tsv"
)


def read_tsv(
    path: Path,
) -> list[dict[str, str]]:
    with path.open(
        newline=""
    ) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


def clean_text(
    value: object,
) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).split()
    )


def main() -> None:
    payload: dict[str, Any] = json.loads(
        QUERY_PATH.read_text()
    )

    query_specs = {
        query["id"]: query
        for query in payload["queries"]
    }

    lexical_rows = read_tsv(
        LEXICAL_PATH
    )

    semantic_rows = read_tsv(
        SEMANTIC_PATH
    )

    lexical_by_key: dict[
        tuple[str, str],
        dict[str, str],
    ] = {}

    lexical_rank_counter: dict[
        str,
        int,
    ] = defaultdict(int)

    for row in lexical_rows:
        query_id = row["query_id"]

        lexical_rank_counter[
            query_id
        ] += 1

        row = dict(row)

        row["lexical_pool_rank"] = str(
            lexical_rank_counter[
                query_id
            ]
        )

        key = (
            query_id,
            row["publication_number"],
        )

        lexical_by_key[key] = row

    semantic_by_key = {
        (
            row["query_id"],
            row["publication_number"],
        ): row
        for row in semantic_rows
    }

    frame = pl.read_parquet(
        SILVER_PATH
    )

    metadata = {
        row["publication_number"]: row
        for row in frame.iter_rows(
            named=True
        )
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_rows = 0
    semantic_only_total = 0

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
                "intent",
                "publication_number",
                "title",
                "buyer_name",
                "buyer_country",
                "procedure_type",
                "cpv_codes",
                "description",
                "lot_description_text",
                "lexical_pool_rank",
                "semantic_pool_rank",
                "semantic_score",
                "strict_match",
                "phrase_match",
                "strict_rank",
                "broad_rank",
                "phrase_rank",
                "source_html_url",
                "relevance",
            ]
        )

        for query_id, query_spec in (
            query_specs.items()
        ):
            keys = {
                key
                for key in lexical_by_key
                if key[0] == query_id
            }

            keys.update(
                key
                for key in semantic_by_key
                if key[0] == query_id
            )

            def sort_key(
                key: tuple[str, str],
            ) -> tuple[int, int, str]:
                lexical = lexical_by_key.get(
                    key
                )

                semantic = semantic_by_key.get(
                    key
                )

                lexical_rank = (
                    int(
                        lexical[
                            "lexical_pool_rank"
                        ]
                    )
                    if lexical is not None
                    else 10_000
                )

                semantic_rank = (
                    int(
                        semantic[
                            "semantic_rank"
                        ]
                    )
                    if semantic is not None
                    else 10_000
                )

                return (
                    min(
                        lexical_rank,
                        semantic_rank,
                    ),
                    lexical_rank
                    + semantic_rank,
                    key[1],
                )

            ordered_keys = sorted(
                keys,
                key=sort_key,
            )

            lexical_count = 0
            semantic_count = 0
            semantic_only_count = 0

            for key in ordered_keys:
                lexical = lexical_by_key.get(
                    key
                )

                semantic = semantic_by_key.get(
                    key
                )

                if lexical is not None:
                    lexical_count += 1

                if semantic is not None:
                    semantic_count += 1

                if (
                    lexical is None
                    and semantic is not None
                ):
                    semantic_only_count += 1
                    semantic_only_total += 1

                publication_number = key[1]

                notice = metadata[
                    publication_number
                ]

                relevance = (
                    lexical["relevance"]
                    if lexical is not None
                    else ""
                )

                writer.writerow(
                    [
                        query_id,
                        query_spec["text"],
                        query_spec["intent"],
                        publication_number,
                        clean_text(
                            notice["title"]
                        ),
                        clean_text(
                            notice["buyer_name"]
                        ),
                        clean_text(
                            notice[
                                "first_buyer_country"
                            ]
                        ),
                        clean_text(
                            notice[
                                "procedure_type"
                            ]
                        ),
                        clean_text(
                            notice["cpv_codes"]
                        ),
                        clean_text(
                            notice["description"]
                        )[:1500],
                        clean_text(
                            notice[
                                "lot_description_text"
                            ]
                        )[:1000],
                        (
                            lexical[
                                "lexical_pool_rank"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        (
                            semantic[
                                "semantic_rank"
                            ]
                            if semantic is not None
                            else ""
                        ),
                        (
                            semantic[
                                "semantic_score"
                            ]
                            if semantic is not None
                            else ""
                        ),
                        (
                            lexical[
                                "strict_match"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        (
                            lexical[
                                "phrase_match"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        (
                            lexical[
                                "strict_rank"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        (
                            lexical[
                                "broad_rank"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        (
                            lexical[
                                "phrase_rank"
                            ]
                            if lexical is not None
                            else ""
                        ),
                        clean_text(
                            notice[
                                "source_html_url"
                            ]
                        ),
                        relevance,
                    ]
                )

                total_rows += 1

            print(
                f"{query_id}: "
                f"lexical={lexical_count}, "
                f"semantic={semantic_count}, "
                f"union={len(ordered_keys)}, "
                f"semantic_only="
                f"{semantic_only_count}"
            )

    print()
    print(
        "=== RETRIEVAL JUDGING UNION ==="
    )

    print(
        f"Rows:          {total_rows}"
    )

    print(
        "Semantic-only: "
        f"{semantic_only_total}"
    )

    print(
        f"Output:        {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
