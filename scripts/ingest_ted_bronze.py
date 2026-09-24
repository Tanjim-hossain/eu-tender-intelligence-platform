from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.models import TedSearchRequest
from tendergraph.storage.bronze import BronzeWriter

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
        limit=20,
    )

    client = TedClient()

    result = client.search(request)

    writer = BronzeWriter()

    artifact = writer.write_search_result(
        result=result,
        request=request,
    )

    print("=== TED BRONZE INGESTION ===")
    print(
        f"Total source matches: "
        f"{result.parsed.total_notice_count}"
    )
    print(
        f"Records ingested: "
        f"{artifact.record_count}"
    )
    print(
        f"Timed out: "
        f"{result.parsed.timed_out}"
    )

    print()
    print(f"Data:     {artifact.data_path}")
    print(
        f"Manifest: {artifact.manifest_path}"
    )
    print(f"SHA-256:  {artifact.sha256}")


if __name__ == "__main__":
    main()
