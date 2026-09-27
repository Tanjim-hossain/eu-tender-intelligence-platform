"""Repair missing/stale embeddings without fetching TED or changing Silver rows."""
import json
from dataclasses import asdict

from tendergraph.database.config import DatabaseSettings
from tendergraph.search.embedding_refresh import reconcile_tender_embeddings


def main() -> None:
    result = reconcile_tender_embeddings(DatabaseSettings())
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
