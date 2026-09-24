from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import TedSearchRequest

FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "notice-type",
]

QUERY = (
    "publication-date = (20260918 <> 20260924) "
    "AND buyer-country IN (BEL NLD DEU ITA)"
)


def main() -> None:
    request = TedSearchRequest(
        query=QUERY,
        fields=FIELDS,
        limit=250,
    )

    client = TedClient()

    accumulated = 0
    total_matches: int | None = None

    print("=== TED ITERATION CHECK ===")

    for page in client.iterate(
        request,
        max_pages=2,
    ):
        count = len(
            page.result.parsed.notices
        )

        accumulated += count

        if total_matches is None:
            total_matches = (
                page.result.parsed
                .total_notice_count
            )

        has_next = bool(
            page.result.parsed
            .iteration_next_token
        )

        print(
            f"Page {page.page_number}: "
            f"{count} records "
            f"| next token: {has_next}"
        )

    print()
    print(
        f"Total source matches: "
        f"{total_matches}"
    )
    print(
        f"Records retrieved in check: "
        f"{accumulated}"
    )


if __name__ == "__main__":
    main()
