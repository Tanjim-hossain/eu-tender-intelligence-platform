from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.lexical import (
    ensure_lexical_search,
)
from tendergraph.search.pooling import (
    fetch_candidate_pool,
)

QUERY_PATH = Path(
    "evaluation/retrieval/queries.json"
)

OUTPUT_PATH = Path(
    "evaluation/retrieval/candidates_lexical.tsv"
)

POOL_LIMIT = 20


def clean_text(
    value: str | None,
) -> str:
    if value is None:
        return ""

    return " ".join(
        value.split()
    )


def main() -> None:
    payload: dict[str, Any] = json.loads(
        QUERY_PATH.read_text()
    )

    queries = payload["queries"]

    settings = DatabaseSettings()

    ensure_lexical_search(settings)

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
                "strict_match",
                "phrase_match",
                "strict_rank",
                "broad_rank",
                "phrase_rank",
                "description",
                "source_html_url",
                "relevance",
            ]
        )

        for query_spec in queries:
            query_id = query_spec["id"]
            query = query_spec["text"]
            intent = query_spec["intent"]

            candidates = fetch_candidate_pool(
                settings,
                query=query,
                limit=POOL_LIMIT,
            )

            total_candidates += len(
                candidates
            )

            print()
            print(
                f"{query_id}: {query}"
            )
            print(
                f"Candidates: {len(candidates)}"
            )

            for rank, candidate in enumerate(
                candidates[:5],
                start=1,
            ):
                print(
                    f"  {rank}. "
                    f"{candidate.publication_number} "
                    f"| {candidate.title}"
                )

            for candidate in candidates:
                description = clean_text(
                    candidate.description
                )

                writer.writerow(
                    [
                        query_id,
                        query,
                        intent,
                        candidate.publication_number,
                        clean_text(
                            candidate.title
                        ),
                        clean_text(
                            candidate.buyer_name
                        ),
                        candidate.buyer_country,
                        candidate.strict_match,
                        candidate.phrase_match,
                        (
                            f"{candidate.strict_rank:.8f}"
                        ),
                        (
                            f"{candidate.broad_rank:.8f}"
                        ),
                        (
                            f"{candidate.phrase_rank:.8f}"
                        ),
                        description[:1000],
                        candidate.source_html_url,
                        "",
                    ]
                )

    print()
    print("=== RETRIEVAL POOL ===")
    print(
        f"Queries:     {len(queries)}"
    )
    print(
        f"Candidates:  {total_candidates}"
    )
    print(
        f"Output:      {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
