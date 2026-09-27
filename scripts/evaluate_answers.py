"""Replay contract cases by default; --live evaluates a local Ollama model."""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from tendergraph.rag.evaluation import check_answer, summarize
from tendergraph.rag.evidence import TenderEvidence
from tendergraph.rag.ollama_provider import OllamaProvider
from tendergraph.rag.prompts import SYSTEM_PROMPT, build_user_prompt
from tendergraph.rag.settings import RAGSettings

ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = ROOT / "evaluation" / "answers"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call local Ollama; no paid provider")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mode = "local_model" if args.live else "contract_replay"
    source = SUITE_DIR / ("quality_cases.json" if args.live else "contract_cases.json")
    suite = json.loads(source.read_text())
    provider = None
    model = None
    if args.live:
        settings = RAGSettings()
        if settings.provider != "ollama":
            parser.error("Live evaluation requires RAG_PROVIDER=ollama and an installed RAG_MODEL")
        model = settings.model
        provider = OllamaProvider(settings)
    rows: list[dict[str, Any]] = []
    try:
        for case in suite["cases"]:
            started = time.perf_counter()
            try:
                if provider is not None:
                    evidence = TypeAdapter(list[TenderEvidence]).validate_python(suite["evidence"])
                    raw = provider.generate(
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=build_user_prompt(question=case["question"], evidence=evidence),
                    )
                else:
                    raw = case["response"]
                result = check_answer(
                    raw, allowed=set(suite["allowed_citations"]),
                    expected_selected=set(case["expected_selected"]),
                    forbidden_phrases=case.get("forbidden_phrases", []),
                )
                if args.live or case["expected_accept"]:
                    passed = all(result[key] for key in (
                        "contract_valid", "selection_match", "phrase_check_passed"
                    ))
                else:
                    passed = not result["contract_valid"]
                rows.append({"id": case["id"], "passed": passed,
                             "latency_ms": (time.perf_counter() - started) * 1000,
                             "review": case.get("review"), **result})
            except (RuntimeError, ValueError) as exc:
                rows.append({"id": case["id"], "passed": False,
                             "error": str(exc), "provider_or_fixture_error": True})
    finally:
        if provider is not None:
            provider.close()
    report: dict[str, Any] = {
        "mode": mode, "model": model, "fixture_data": "synthetic",
        "created_at": datetime.now(UTC).isoformat(),
        "human_factual_review_required": bool(args.live),
        "scope": ("Hand-authored output replay; no LLM or database called." if not args.live
                  else "Local model on fixed synthetic evidence; does not measure retrieval or factual entailment."),
        "summary": summarize(rows), "cases": rows,
    }
    output = args.output or SUITE_DIR / "reports" / f"{mode}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"mode": mode, **report["summary"], "output": str(output)}, indent=2))
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
