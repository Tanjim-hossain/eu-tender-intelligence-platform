from __future__ import annotations

import argparse

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.lexical import (
    ensure_lexical_search,
    search_tenders,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search TED notices with the "
            "PostgreSQL lexical baseline."
        )
    )

    parser.add_argument(
        "query",
        help="Natural-language tender search query",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    settings = DatabaseSettings()

    ensure_lexical_search(
        settings
    )

    results = search_tenders(
        settings,
        query=args.query,
        limit=args.limit,
    )

    print(
        "=== TENDERGRAPH LEXICAL SEARCH ==="
    )

    print(
        f"Query:   {args.query}"
    )

    print(
        f"Results: {len(results)}"
    )

    for index, result in enumerate(
        results,
        start=1,
    ):
        print()
        print(
            f"{index}. {result.title}"
        )
        print(
            "   Publication: "
            f"{result.publication_number}"
        )
        print(
            "   Date:        "
            f"{result.publication_date}"
        )
        print(
            "   Buyer:       "
            f"{result.buyer_name}"
        )
        print(
            "   Country:     "
            f"{result.buyer_country}"
        )
        print(
            "   Procedure:   "
            f"{result.procedure_type}"
        )
        print(
            "   Rank:        "
            f"{result.rank:.6f}"
        )

        if result.estimated_value is not None:
            print(
                "   Value:       "
                f"{result.estimated_value} "
                f"{result.estimated_value_currency}"
            )

        if result.earliest_deadline is not None:
            print(
                "   Deadline:    "
                f"{result.earliest_deadline}"
            )

        print(
            "   Source:      "
            f"{result.source_html_url}"
        )


if __name__ == "__main__":
    main()
