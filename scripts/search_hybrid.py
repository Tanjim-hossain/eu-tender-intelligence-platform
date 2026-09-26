from __future__ import annotations

import argparse

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.service import (
    HybridSearchService,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "query",
        help="Natural-language tender query",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    service = HybridSearchService(
        DatabaseSettings()
    )

    results = service.search(
        args.query,
        limit=args.limit,
    )

    for rank, result in enumerate(
        results,
        start=1,
    ):
        print()
        print(
            f"{rank}. "
            f"{result.publication_number}"
        )
        print(
            f"   {result.title}"
        )
        print(
            "   RRF:",
            f"{result.rrf_score:.6f}",
        )
        print(
            "   lexical_rank:",
            result.lexical_rank,
        )
        print(
            "   semantic_rank:",
            result.semantic_rank,
        )

        if (
            result.semantic_score
            is not None
        ):
            print(
                "   semantic_score:",
                f"{result.semantic_score:.6f}",
            )


if __name__ == "__main__":
    main()
