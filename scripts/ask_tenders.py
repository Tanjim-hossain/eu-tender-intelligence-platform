"""Ask the running local TenderGraph API; the server chooses the answer mode."""

from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--query", help="Optional short retrieval query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        response = httpx.post(
            args.url.rstrip("/") + "/ask",
            json={
                "question": args.question,
                "query": args.query,
                "evidence_limit": args.limit,
                "retrieval_depth": args.depth,
            },
            timeout=660,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        parser.exit(1, f"API error {exc.response.status_code}: {exc.response.text}\n")
    except httpx.HTTPError:
        parser.exit(1, "Cannot reach TenderGraph. Start the API and try again.\n")
    data = response.json()
    if args.as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Mode: {data['mode']} | Status: {data['status']}\n")
        print(data["answer"])
        print("\nSources:")
        for source in data["sources"]:
            print(f"[{source['citation_id']}] {source['source_html_url']}")
        if data["context_truncated"]:
            print("\nSome source text was shortened to fit the context budget.")


if __name__ == "__main__":
    main()
