from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import TedSearchRequest


def main() -> None:
    request = TedSearchRequest(
        query=(
            "publication-date = "
            "(20260918 <> 20260924) "
            "AND buyer-country "
            "IN (BEL NLD DEU ITA)"
        ),
        fields=[
            "publication-number",
            "publication-date",
            "notice-title",
            "buyer-name",
            "buyer-country",
            "classification-cpv",
            "notice-type",
        ],
        limit=5,
    )

    client = TedClient()

    result = client.search(request)

    print("=== PRODUCTION CLIENT CHECK ===")
    print(
        f"Total matches: "
        f"{result.parsed.total_notice_count}"
    )
    print(
        f"Downloaded: "
        f"{len(result.parsed.notices)}"
    )
    print(
        f"Timed out: "
        f"{result.parsed.timed_out}"
    )

    print("\nNotices:")

    for notice in result.parsed.notices:
        title = notice.notice_title.get(
            "eng",
            next(
                iter(notice.notice_title.values()),
                "No title",
            ),
        )

        print(
            f"- {notice.publication_number} "
            f"| {notice.buyer_country} "
            f"| {title[:100]}"
        )


if __name__ == "__main__":
    main()
